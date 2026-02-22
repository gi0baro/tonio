{{ _refv = list(filter(lambda v: v[0] == "AsyncIO", _data))[0][1][_ckey][_dkey]["rps"] }}
| Runtime | Total requests | Throughput | Mean latency | 99p latency | Latency stdev |
| --- | --- | --- | --- | --- | --- |
{{ for label, bdata in _data: }}
{{ lbdata = bdata[_ckey][_dkey] }}
| {{ =label }} | {{ =lbdata["messages"] }} | {{ =lbdata["rps"] }} ({{ =round(lbdata["rps"] / _refv, 2) }}x) | {{ =f"{lbdata['latency_mean']}ms" }} | {{ =f"{lbdata['latency_percentiles'][-1][1]}ms" }} | {{ =lbdata["latency_std"] }} |
{{ pass }}
