import assert from "node:assert/strict";
import test from "node:test";
import { decidePersonalWorkspaceAccess } from "./scripts/connect-personal-workspace.mjs";

test("requests access only when there is no existing Personal Workspace record", () => {
  assert.deepEqual(decidePersonalWorkspaceAccess([]), { action: "grant" });
  assert.deepEqual(
    decidePersonalWorkspaceAccess([{ workspaceKind: "organization", status: "GRANTED" }]),
    { action: "grant" },
  );
});

test("reuses an existing granted or pending Personal Workspace record", () => {
  assert.deepEqual(
    decidePersonalWorkspaceAccess([{ id: "access-1", workspaceKind: "personal", status: "GRANTED" }]),
    { action: "already-granted", accessId: "access-1" },
  );
  assert.deepEqual(
    decidePersonalWorkspaceAccess([{ id: "access-2", workspaceKind: "personal", status: "PENDING" }]),
    { action: "pending", accessId: "access-2" },
  );
});

test("does not silently retry denied or unknown Personal Workspace access", () => {
  assert.deepEqual(
    decidePersonalWorkspaceAccess([{ id: "access-3", workspaceKind: "personal", status: "DENIED" }]),
    { action: "blocked", accessId: "access-3", status: "DENIED" },
  );
  assert.throws(() => decidePersonalWorkspaceAccess(null), /must be an array/);
});
