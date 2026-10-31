# Vast.ai price-selection benchmark: one H100 SXM 80GB, on demand

**What this is:** a read-only look at public Vast.ai listings, measuring how much a buyer saves by **selecting** the cheapest offer that meets fixed requirements instead of a typical (median) one, at the same moment.

**What this is not:** a negotiation. No offer, bid, rental or payment was made, and no account or API key was used. Nothing here is a negotiated discount, and it says nothing about our simulated supplier concessions.

## Method

- **Source:** `GET https://console.vast.ai/api/v0/bundles/?q={"gpu_name":{"eq":"H100 SXM"},"num_gpus":{"eq":1},"rentable":{"eq":true},"type":"on-demand"}`, unauthenticated.
- **Snapshots:** three, two minutes apart: 2026-10-31 10:42:39, 10:44:40 and 10:46:40 UTC. All returned HTTP 200 and `truncated: false`, with 12, 12 and 11 listings.
- **Raw data:** the responses are stored in `snapshots/`, with each host's `public_ipaddr` removed. `offers.csv` has one row per listing per snapshot, with eligibility and the reason for each exclusion. `results.json` has the computed figures.
- **Price:** the listed `dph_total`, in USD per hour, kept in USD with no FX conversion. Per each offer's `search` field, it is the GPU rate (`dph_base`) plus a small default-disk amount (`diskHour`, USD 0.0015–0.0076 per hour across these offers). Storage beyond that default (`storage_cost`) and transfer (USD per TB, up and down) are listed per offer below but **not** added. All claims are limited to the listed hourly rate.
- **Unit of comparison:** the machine, not the listing. Offer IDs change between snapshots (35 listings, 23 offer IDs, 12 machines, 7 hosts), and one host can list several machines.

### Requirements, declared before ranking

| Rule | Strict | Without verified host |
|---|---|---|
| GPU | 1x H100 SXM, at least 80,000 MB | same |
| Type | on demand, not interruptible | same |
| Host verified by Vast.ai | **required** | not required |
| Reliability | at least 0.98 | same |
| CPU cores (effective) | at least 16 | same |
| RAM | at least 64 GB | same |
| Disk | at least 200 GB | same |
| Region | any | any |

The second set is the strict set with one rule removed. It's reported next to the strict set to show how much that rule drives the result. It isn't a choice made after looking at prices.

## Results

| Snapshot (UTC) | Set | Eligible offers / hosts | Cheapest | Median offer | Cheapest vs median offer | Median of hosts' cheapest | Cheapest vs median host |
|---|---|---|---|---|---|---|---|
| 10:42 | strict | 4 / 3 | 2.1356 | 2.1689 | 1.5% | 2.2022 | 3.0% |
| 10:44 | strict | 4 / 3 | 2.1356 | 2.1689 | 1.5% | 2.2022 | 3.0% |
| 10:46 | strict | 3 / 2 | 2.1356 | 2.1356 | 0.0% | 3.0636 | 30.3% (2 hosts only) |
| 10:42 | without verified host | 8 / 5 | 1.9342 | 2.3019 | 16.0% | 2.2022 | 12.2% |
| 10:44 | without verified host | 8 / 5 | 1.9342 | 2.3019 | 16.0% | 2.2022 | 12.2% |
| 10:46 | without verified host | 7 / 4 | 1.9342 | 2.4015 | 19.5% | 2.2685 | 14.7% |

Prices are in USD per hour.

- **Selected price, strict:** USD 2.1356/h, from machine 150576 (host 638511, Germany, reliability 0.9951), in all three snapshots.
- **Selected price, without verified host:** USD 1.9342/h, from machine 153324 (host 169960, India, unverified, reliability 0.9934).

### Eligible offers (by machine; price per snapshot, USD/h)

| Machine | Host | Location | Verification | Reliability | CPU cores | RAM GB | Disk GB | dph_total per snapshot | Storage USD/GB/month (as listed) | Transfer USD/TB up / down |
|---|---|---|---|---|---|---|---|---|---|---|
| 153324 | 169960 | India, IN | unverified | 0.9934 | 24 | 290 | 322 | 1.9342, 1.9342, 1.9342 | 0.200 | 4.00 / 2.67 |
| 150576 | 638511 | Germany, DE | verified | 0.9951 | 24 | 125 | 358 | 2.1356, 2.1356, 2.1356 | 0.200 | 4.00 / 2.67 |
| 149868 | 638511 | Latvia, LV | verified | 0.9941 | 24 | 94 | 706 | 2.1356, 2.1356, 2.1356 | 0.200 | 4.00 / 2.67 |
| 154313 | 161249 | Idaho, US | verified | 0.9894 | 48 | 160 | 10712 | 2.2022, 2.2022 (gone in the 3rd) | 0.200 | 4.00 / 2.67 |
| 154060 | 743471 | Japan, JP | unverified | 0.9891 | 28 | 257 | 754 | 2.4015, 2.4015, 2.4015 | 0.133 | 0.00 / 0.00 |
| 154041 | 743471 | Japan, JP | unverified | 0.9890 | 28 | 257 | 735 | 2.4015, 2.4015, 2.4015 | 0.133 | 0.00 / 0.00 |
| 154066 | 743471 | Japan, JP | unverified | 0.9878 | 28 | 257 | 782 | 2.4015, 2.4015, 2.4015 | 0.133 | 0.00 / 0.00 |
| 140932 | 214845 | Czechia, CZ | verified | 0.9914 | 24 | 108 | 931 | 4.0316, 3.9916, 3.9916 | 0.680 | 33.33 / 40.00 |

All eight are eligible without the verified-host rule. Only the four verified machines (150576, 149868, 154313, 140932) are eligible under the strict set.

### Excluded under the strict set (first failed rule)

| Machine | Host | Location | dph_total | Reason |
|---|---|---|---|---|
| 153324 | 169960 | India, IN | 1.9342 | host unverified |
| 41011 | 161249 | Idaho, US | 2.2022 | host deverified |
| 154060, 154041, 154066, 155838 | 743471 | Japan, JP | 2.4015 | host unverified |
| 148471 | 517294 | Australia, AU | 2.9327 | 8 effective CPU cores |
| 152562 | 719241 | Germany, DE | 4.0015 | host unverified |

Machine 155838 is also excluded without the verified-host rule (reliability 0.9191), as are 41011 (reliability 0.9716) and 152562 (disk 57 GB).

## What the numbers support

- **Under strict requirements, selection saves little:** the cheapest eligible offer is 0–1.5% below the median eligible offer, or 3% below the median host. The 30.3% in the third snapshot is the midpoint of only two hosts' prices, so it isn't meaningful.
- **Most of the visible spread comes from accepting unverified hosts.** Without that rule, the cheapest offer is 16–19.5% below the median offer, at the cost of an unverified host.
- **Prices were stable over four minutes.** The cheapest prices didn't change, and one machine dropped out of the listings.

## Limits

- **Tiny sample:** one GPU model, one point in time (four minutes), 12 machines and 7 hosts, of which only 2–3 hosts are eligible under the strict set. Repeated snapshots of the same machines are not independent samples.
- **Listed rates only:** storage and transfer are excluded, and they differ a lot between hosts. Machine 140932 charges USD 33–40 per TB of transfer, against 0–4 elsewhere, so total cost depends on the workload.
- **No acceptance proven:** a listed price is not an accepted order. Nothing was rented, so availability at that price isn't verified.
- **Field semantics come from field names and values,** not from Vast.ai documentation. In particular, storage is read as USD per GB per month.
- **Not a negotiation result.** It shows a price-selection opportunity in public listings. It doesn't show savings from our negotiation engine, and the engine wasn't run against Vast.ai.

## Reproduce

```sh
cd benchmarks/vastai
python3 benchmark.py fetch --snapshots 3 --interval-s 120   # public GET only; writes snapshots/
python3 benchmark.py analyze                                # writes offers.csv and results.json
```

Python 3.10+, standard library only. A fresh fetch gives different numbers, because listings change.
