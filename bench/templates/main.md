# TonIO benchmarks

Run at: {{ =datetime.datetime.fromtimestamp(data.run_at).strftime('%a %d %b %Y, %H:%M') }}    
Environment: {{ =benv }} (CPUs: {{ =data.cpu }})    
Python version: {{ =data.pyver }}    
TonIO version: {{ =data.tonio }}    

### Running 1 million coroutines

Time to run 1 million coroutines (lower is better).

{{ _data = data.results["1m"] }}
{{ _refv = list(filter(lambda v: v[0] == "AsyncIO", _data))[0][1][2] }}

| Runtime | Creation time | Exec time | Total time |
| --- | --- | --- | --- |
{{ for label, res in _data: }}
| {{ =label }} | {{ =round(res[0] * 1000, 3) }}ms | {{ =round(res[1] * 1000, 3) }}ms | {{ =round(res[2] * 1000, 3) }}ms ({{ =round(_refv / res[2], 2) }}x) |
{{ pass }}

### Sockets

TCP echo server with raw sockets comparison using 1KB, 10KB and 100KB messages.

{{ _data = data.results["net_sock"] }}
{{ _refv = lambda mkey: list(filter(lambda v: v[0] == "AsyncIO", _data))[0][1]["4"][mkey]["rps"] }}

| Runtime | Throughput (1KB) | Throughput (10KB) | Throughput (100KB) |
| --- | --- | --- | --- |
{{ for label, res in _data: }}
| {{ =label }} | {{ for mkey in res["4"].keys(): }}{{ =res["4"][mkey]["rps"] }} ({{ =round(res["4"][mkey]["rps"] / _refv(mkey), 2) }}x) | {{ pass }}
{{ pass }}

#### 1KB details

{{ _dkey, _ckey = "1024", "4" }}
{{ include "./_net_table.tpl" }}

#### 10KB details

{{ _dkey, _ckey = "10240", "4" }}
{{ include "./_net_table.tpl" }}

#### 100KB details

{{ _dkey, _ckey = "102400", "4" }}
{{ include "./_net_table.tpl" }}

### Concurrency

#### 1 million coros

{{ _data = data.results["concurrency"]["1m"] }}

| Mode | Threads | Total time |
| --- | --- | --- |
{{ for label, threads, res in _data: }}
| {{ =label }} | {{ =threads }} | {{ =round(res[2] * 1000, 3) }}ms |
{{ pass }}

#### Sockets

{{ _data = data.results["concurrency"]["net_sock"] }}

| Mode | Threads | Throughput (10KB) |
| --- | --- | --- |
{{ for label, threads, res in _data: }}
| {{ =label }} | {{ =threads }} | {{ =res["4"]["10240"]["rps"] }} |
{{ pass }}
