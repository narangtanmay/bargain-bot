# Third-party attribution and MIT license

Parts of the negotiation policy, protocol, simulated supplier behavior and tactician pattern are adapted from [the upstream buyer-agent repository](https://github.com/Jaseelkt007/tacto-buyer-agent), by Jaseelkt007 and SiddharthPachpor, based on the Tacto Negotiation Arena starter kit. The upstream source was originally reviewed at commit `807696f`. The applicable MIT copyright and permission notice is reproduced verbatim below. Upstream data and documentation are licensed separately under CC BY 4.0 and are not distributed here.

## Adapted components

| Local component | Upstream component |
|---|---|
| `buyer.py` price ladder, readiness, auction, bidder drop, rival citation, final-offer discipline | Buyer policy module and deterministic closing move |
| `protocol.py` thread helpers and message shape | Arena thread protocol and standing-offer helpers |
| `table.py` negotiation loop | Arena runner, adapted to in-process suppliers |
| `checks.py` structured must-have operators | Structured commercial-term comparisons |
| `suppliers.py` concession schedule | Supplier gym and arena simulator |
| `reader.py` source-quotation validation pattern | Supplier reply interpreter |
| `tactician.py` model-selected, code-priced options | Hybrid tactician pattern |

The request/JSON integration, shared accept/checker gate, simulation personas, Ed25519 confirmation integrity, result contract, Sokosumi worker and Masumi integration contain project-specific implementation. Adaptations and source links remain identified in the modules. The upstream attribution does not imply endorsement or independent supplier validation.

## MIT License

```
MIT License

Copyright (c) 2026 Tacto Technology GmbH

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```
