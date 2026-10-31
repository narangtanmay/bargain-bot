import hashlib
import os
from pathlib import Path

import pytest

from negotiator.__main__ import main

ROOT = Path(__file__).resolve().parent.parent

# SHA-256 of the result file `negotiation-coworker` writes for each example and seed (pinned at `dc9ef0e`).
# With the LLM flag off, this branch must write the same bytes, `log_hash` included.
MAIN_DIGESTS = {
    ("request-above-cap.txt", 1): "7b074419bbabe33dd046ced9b9d2c87b2bbb3cf45bdf7b189214d4bc8abb2d54",
    ("request-above-cap.txt", 2): "4c6a10fdcdd5070cff4adc2a314f44f15980dc423828959c13cb9d672fb78884",
    ("request-above-cap.txt", 3): "79686f267f57c60ce46808fd1ed7e3cc9b3e70711df61c6a951314eaee59ee67",
    ("request-broken-quote.txt", 1): "6a0364ff1847435c8563d63a0aac654fe4f28da71235c355afd68e07489a3546",
    ("request-broken-quote.txt", 2): "bfbf2ae74000a66566a67c54129a4fb64de104136329212950d2dd0f654b1888",
    ("request-broken-quote.txt", 3): "16b58c7cdde6ec6bb877fe29f2e8af6d5d5ae77199b9e6bae176eac0b298407c",
    ("request-normal.txt", 1): "cb16efa80b19e29493a41d151e69c4cbc6fc4d38af09b104998f5de0d30a9d5b",
    ("request-normal.txt", 2): "a5358ee01b3b195a8047b636cfcaffc2e25bbf2a44f12f9e5261f30a54adde84",
    ("request-normal.txt", 3): "6517c15e7e113b0aab7f5a10ed6c78de300b5c2c5b5cb9a7338a249930e7cbdc",
    ("request-real-quotes.txt", 1): "674a29ea04fc4d7be5b0c35199ddd8025d642de92e4fb6b9013e4a0d9713ec18",
    ("request-real-quotes.txt", 2): "ce1804c556f8ae7390523cf0091ec1249c76dddf7610849f33e8b63db8079508",
    ("request-real-quotes.txt", 3): "1aa73f8f42c704e22b73431aad33b057cad98aed4c4cd986b2a6fddc540a1396",
    ("request.txt", 1): "cb16efa80b19e29493a41d151e69c4cbc6fc4d38af09b104998f5de0d30a9d5b",
    ("request.txt", 2): "a5358ee01b3b195a8047b636cfcaffc2e25bbf2a44f12f9e5261f30a54adde84",
    ("request.txt", 3): "6517c15e7e113b0aab7f5a10ed6c78de300b5c2c5b5cb9a7338a249930e7cbdc",
}


# Exact Windows output bytes captured from main 6fac749 (Path.write_text uses CRLF).
MAIN_DIGESTS_WINDOWS = {
    ('request-above-cap.txt', 1): '27251308f2d1925e0010f72787b86660ed8ed93be05bbf84ba15990d5c930e95',
    ('request-above-cap.txt', 2): 'a859272c67221952f85fc209ff16835c1e87029cb493a65c008ef4623a9a4504',
    ('request-above-cap.txt', 3): '3ae53133c0cab8da6a8366e8a2635669a88449305b3c58e2ef68a653b18955d2',
    ('request-broken-quote.txt', 1): 'a9a6cbbb8b0cd0b7f638149d6f0821bdc9fee6a6502b43d74616c9bac8e56041',
    ('request-broken-quote.txt', 2): '21b89230d22bf97d1ebc70846d408fb29244ffdacfc7cc42ab726acf6a5feee9',
    ('request-broken-quote.txt', 3): '5aeef8e78c544a1d4a5b1b2eb3b97f69b8f314bcccaa9891861387fa0989cbd6',
    ('request-normal.txt', 1): '0a82653e39806fb5cc2a38dc73123df806725fd955274aedd95e6770cf146458',
    ('request-normal.txt', 2): 'e7022f55e1f3f4862ab914401b557b4b0097fdcf40ed9dabbf50a420e5d0130e',
    ('request-normal.txt', 3): 'c76d4ef8d1753a2623835575262fb8997dbb2c97762fd14c15a5f64f682d1449',
    ('request-real-quotes.txt', 1): '4e9b9618055e336d88a752ebf9ca40e3798ef3b13ed961c3c03f51e2ccd8c306',
    ('request-real-quotes.txt', 2): 'd0ec114aaca6bce492bbf160fa99dca9774dbf66f8a75e4af1b473ab3d2a2b70',
    ('request-real-quotes.txt', 3): '47464051fee97fdf5102b4080dbefb8e47429744dcaba7c2d873a72205624bf3',
    ('request.txt', 1): '0a82653e39806fb5cc2a38dc73123df806725fd955274aedd95e6770cf146458',
    ('request.txt', 2): 'e7022f55e1f3f4862ab914401b557b4b0097fdcf40ed9dabbf50a420e5d0130e',
    ('request.txt', 3): 'c76d4ef8d1753a2623835575262fb8997dbb2c97762fd14c15a5f64f682d1449',
}


@pytest.mark.parametrize("flag", [None, "off", "OFF", ""])
def test_flag_off_writes_the_same_bytes_as_main(tmp_path, monkeypatch, flag):
    if flag is None:
        monkeypatch.delenv("NEGOTIATOR_LLM", raising=False)
    else:
        monkeypatch.setenv("NEGOTIATOR_LLM", flag)
    for (name, seed), digest in MAIN_DIGESTS.items():
        path = ROOT / "examples" / name
        scenario = next((l.split(":", 1)[1].strip() for l in path.read_text().splitlines()
                         if l.lower().startswith("scenario:")), "normal")
        out = tmp_path / "r.json"
        main(["--request-file", str(path), "--out", str(out), "--seed", str(seed)]
             + (["--scenario", scenario] if scenario != "normal" else []))
        expected = MAIN_DIGESTS_WINDOWS[(name, seed)] if os.name == "nt" else digest
        assert hashlib.sha256(out.read_bytes()).hexdigest() == expected, (name, seed)
