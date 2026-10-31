import { existsSync, readFileSync } from "node:fs";
import { homedir } from "node:os";
import { join, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const COWORKER_ID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/iu;
const CLI_VERSION = "1.0.4";

export function decidePersonalWorkspaceAccess(rows) {
  if (!Array.isArray(rows)) {
    throw new TypeError("Workspace access rows must be an array");
  }

  const personalAccess = rows.find((row) => row?.workspaceKind === "personal");
  if (!personalAccess) return { action: "grant" };

  const status = String(personalAccess.status || "").toUpperCase();
  if (status === "GRANTED") {
    return { action: "already-granted", accessId: personalAccess.id };
  }
  if (status === "PENDING") {
    return { action: "pending", accessId: personalAccess.id };
  }
  return {
    action: "blocked",
    accessId: personalAccess.id,
    status: status || "UNKNOWN",
  };
}

function parseArgs(argv) {
  const options = {};
  for (let index = 0; index < argv.length; index += 1) {
    const flag = argv[index];
    if (flag === "--help" || flag === "-h") {
      return { help: true };
    }
    if (flag !== "--coworker-id" && flag !== "--vendor-id") {
      throw new Error(`Unknown option: ${flag}`);
    }
    const value = argv[index + 1];
    if (!value || value.startsWith("--")) {
      throw new Error(`Missing value for ${flag}`);
    }
    options[flag.slice(2)] = value;
    index += 1;
  }

  for (const key of ["coworker-id", "vendor-id"]) {
    if (!COWORKER_ID_PATTERN.test(options[key] || "")) {
      throw new Error(`--${key} must be a UUID`);
    }
  }
  return options;
}

function resolveCliRoot() {
  const configuredRoot = process.env.SOKOSUMI_CLI_ROOT;
  const roamingAppData = process.env.APPDATA || join(homedir(), "AppData", "Roaming");
  const candidates = [
    configuredRoot,
    join(roamingAppData, "npm", "node_modules", "@masumi_network", "sokosumi"),
  ].filter(Boolean);

  const root = candidates.find((candidate) => existsSync(join(candidate, "package.json")));
  if (!root) {
    throw new Error("Could not find the global Sokosumi CLI package; install CLI 1.0.4 first");
  }
  return root;
}

async function importCliModule(root, relativePath) {
  return import(pathToFileURL(join(root, "dist", "src", relativePath)).href);
}

async function listWorkspaceAccess(client, coworkerId, parseApiResponse) {
  const rows = [];
  const seenCursors = new Set();
  let cursor;

  for (let page = 0; page < 50; page += 1) {
    const query = new URLSearchParams({ limit: "20" });
    if (cursor) query.set("cursor", cursor);
    const response = parseApiResponse(
      await client.get(`/v1/coworkers/${encodeURIComponent(coworkerId)}/workspace-access?${query}`),
    );
    if (!Array.isArray(response.data)) {
      throw new Error("Core returned an invalid Coworker access list");
    }
    rows.push(...response.data);

    const nextCursor = response.meta?.pagination?.nextCursor;
    if (typeof nextCursor !== "string" || !nextCursor) return rows;
    if (seenCursors.has(nextCursor)) {
      throw new Error("Core returned a repeated access-list cursor");
    }
    seenCursors.add(nextCursor);
    cursor = nextCursor;
  }

  throw new Error("Coworker access list exceeded the safe pagination limit");
}

function printResult({ coworkerId, vendorId, access }) {
  process.stdout.write(`${JSON.stringify({
    target: "preprod",
    coworkerId,
    vendorId,
    access: {
      id: access.id,
      status: access.status,
      workspaceId: access.workspaceId,
      workspaceKind: "personal",
    },
  }, null, 2)}\n`);
}

async function main(argv) {
  const options = parseArgs(argv);
  if (options.help) {
    process.stdout.write(
      "Usage: node scripts/connect-personal-workspace.mjs --coworker-id UUID --vendor-id UUID\n" +
        "Uses the Sokosumi CLI 1.0.4 Preprod account session to inspect and, if needed, grant Personal Workspace access.\n" +
        "It never prints or stores an authentication token.\n",
    );
    return;
  }

  const cliRoot = resolveCliRoot();
  const packageMetadata = JSON.parse(readFileSync(join(cliRoot, "package.json"), "utf8"));
  if (packageMetadata.version !== CLI_VERSION) {
    throw new Error(`This helper requires Sokosumi CLI ${CLI_VERSION}; found ${packageMetadata.version}`);
  }

  const [bootstrap, http, identities, coworkers, personalWorkspace, apiResponse] = await Promise.all([
    importCliModule(cliRoot, "auth/bootstrap.js"),
    importCliModule(cliRoot, "api/http-client.js"),
    importCliModule(cliRoot, "api/services/user-identity-service.js"),
    importCliModule(cliRoot, "api/services/coworker-service.js"),
    importCliModule(cliRoot, "api/services/personal-workspace-service.js"),
    importCliModule(cliRoot, "api/models/api-response.js"),
  ]);

  // Use the CLI's supported credential manager without allowing shell env tokens to override it.
  const environment = { ...process.env };
  delete environment.SOKOSUMI_API_KEY;
  delete environment.SOKOSUMI_AUTH_TOKEN;
  const session = bootstrap.bootstrapCliSession({
    environment,
    loadFiles: false,
    preprod: true,
  });
  await bootstrap.requireAuthenticatedSession(session);

  const client = http.createCoreHttpClient({
    apiUrl: session.config.apiUrl,
    authBaseUrl: session.config.authBaseUrl,
    clientId: session.config.clientId,
    clientSecret: session.config.clientSecret,
    authManager: session.authManager,
    environment: session.env,
  });

  const identity = await identities.fetchUserIdentity(client);
  const { coworker } = await coworkers.fetchCoworker(client, options["coworker-id"]);
  if (coworker.vendor?.id !== options["vendor-id"]) {
    throw new Error("Coworker does not belong to the supplied Vendor ID");
  }
  if (!coworker.capabilities?.includes("tasks")) {
    throw new Error("Coworker does not have the tasks capability");
  }
  if (coworker.isWhitelisted !== false) {
    throw new Error("Coworker is not marked private; stopping before changing Workspace access");
  }

  const { parseApiResponse } = apiResponse;
  const currentRows = await listWorkspaceAccess(client, coworker.id, parseApiResponse);
  const decision = decidePersonalWorkspaceAccess(currentRows);

  if (decision.action === "already-granted") {
    const existing = currentRows.find((row) => row.id === decision.accessId);
    await personalWorkspace.verifyPersonalWorkspace(client, existing.workspaceId);
    printResult({ coworkerId: coworker.id, vendorId: coworker.vendor.id, access: existing });
    return;
  }
  if (decision.action === "pending") {
    const existing = currentRows.find((row) => row.id === decision.accessId);
    printResult({ coworkerId: coworker.id, vendorId: coworker.vendor.id, access: existing });
    return;
  }
  if (decision.action === "blocked") {
    throw new Error(`Existing Personal Workspace access is ${decision.status}; no duplicate request was made`);
  }

  const { access } = await coworkers.grantCoworkerWorkspaceAccess(
    client,
    coworker.id,
    { userId: identity.id },
  );
  if (!["GRANTED", "PENDING"].includes(access.status)) {
    throw new Error(`Core returned Personal Workspace access status ${access.status}`);
  }
  if (access.coworkerId !== coworker.id) {
    throw new Error("Core returned access for a different Coworker");
  }
  if (access.status === "GRANTED") {
    await personalWorkspace.verifyPersonalWorkspace(client, access.workspaceId);
  }

  printResult({ coworkerId: coworker.id, vendorId: coworker.vendor.id, access });
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try {
    await main(process.argv.slice(2));
  } catch (error) {
    const status = Number.isInteger(error?.status) ? ` (Core HTTP ${error.status})` : "";
    process.stderr.write(`Personal Workspace access setup failed${status}. No credential was printed.\n`);
    process.exitCode = 1;
  }
}
