# TonIO benchmarks

Run at: Mon 02 Mar 2026, 23:15    
Environment: AMD Ryzen 7 5700X @ Gentoo Linux 6.12.74 (CPUs: 16)    
Python version: 3.14    
TonIO version: 0.2.0    

### Running 1 million coroutines

Time to run 1 million coroutines (lower is better).


| Runtime | Creation time | Exec time | Total time |
| --- | --- | --- | --- |
| TonIO yield | 103.857ms | 606.632ms | 710.489ms (4.14x) |
| TonIO async | 92.139ms | 1041.824ms | 1133.963ms (2.59x) |
| TonIO yield (context) | 99.632ms | 762.757ms | 862.389ms (3.41x) |
| TonIO async (context) | 82.447ms | 1172.767ms | 1255.214ms (2.34x) |
| AsyncIO | 39.064ms | 2898.894ms | 2937.958ms (1.0x) |
| Trio | 2244.962ms | 5304.976ms | 7549.937ms (0.39x) |
| TinyIO | 72.451ms | 3217.046ms | 3289.497ms (0.89x) |

### Sockets

TCP echo server with raw sockets comparison using 1KB, 10KB and 100KB messages.


| Runtime | Throughput (1KB) | Throughput (10KB) | Throughput (100KB) |
| --- | --- | --- | --- |
| TonIO yield | 151981.0 (2.79x) | 135615.3 (2.87x) | 47575.7 (1.75x) | 
| TonIO async | 118059.7 (2.16x) | 97448.2 (2.07x) | 40365.2 (1.49x) | 
| TonIO yield (context) | 154921.6 (2.84x) | 135429.1 (2.87x) | 48042.5 (1.77x) | 
| TonIO async (context) | 116612.6 (2.14x) | 97723.4 (2.07x) | 41155.0 (1.51x) | 
| AsyncIO | 54567.6 (1.0x) | 47188.9 (1.0x) | 27166.7 (1.0x) | 
| Trio | 81867.6 (1.5x) | 70548.4 (1.5x) | 34110.3 (1.26x) | 

#### 1KB details

| Runtime | Total requests | Throughput | Mean latency | 99p latency | Latency stdev |
| --- | --- | --- | --- | --- | --- |
| TonIO yield | 1519810 | 151981.0 (2.79x) | 0.023ms | 0.046ms | 0.006 |
| TonIO async | 1180597 | 118059.7 (2.16x) | 0.031ms | 0.048ms | 0.003 |
| TonIO yield (context) | 1549216 | 154921.6 (2.84x) | 0.023ms | 0.046ms | 0.006 |
| TonIO async (context) | 1166126 | 116612.6 (2.14x) | 0.031ms | 0.048ms | 0.004 |
| AsyncIO | 545676 | 54567.6 (1.0x) | 0.071ms | 0.089ms | 0.004 |
| Trio | 818676 | 81867.6 (1.5x) | 0.047ms | 0.07ms | 0.01 |


#### 10KB details

| Runtime | Total requests | Throughput | Mean latency | 99p latency | Latency stdev |
| --- | --- | --- | --- | --- | --- |
| TonIO yield | 1356153 | 135615.3 (2.87x) | 0.03ms | 0.046ms | 0.002 |
| TonIO async | 974482 | 97448.2 (2.07x) | 0.04ms | 0.05ms | 0.001 |
| TonIO yield (context) | 1354291 | 135429.1 (2.87x) | 0.03ms | 0.044ms | 0.002 |
| TonIO async (context) | 977234 | 97723.4 (2.07x) | 0.04ms | 0.051ms | 0.002 |
| AsyncIO | 471889 | 47188.9 (1.0x) | 0.084ms | 0.102ms | 0.006 |
| Trio | 705484 | 70548.4 (1.5x) | 0.055ms | 0.08ms | 0.011 |


#### 100KB details

| Runtime | Total requests | Throughput | Mean latency | 99p latency | Latency stdev |
| --- | --- | --- | --- | --- | --- |
| TonIO yield | 475757 | 47575.7 (1.75x) | 0.082ms | 0.12ms | 0.008 |
| TonIO async | 403652 | 40365.2 (1.49x) | 0.097ms | 0.119ms | 0.008 |
| TonIO yield (context) | 480425 | 48042.5 (1.77x) | 0.081ms | 0.109ms | 0.007 |
| TonIO async (context) | 411550 | 41155.0 (1.51x) | 0.095ms | 0.11ms | 0.006 |
| AsyncIO | 271667 | 27166.7 (1.0x) | 0.145ms | 0.169ms | 0.01 |
| Trio | 341103 | 34110.3 (1.26x) | 0.115ms | 0.164ms | 0.021 |


### Concurrency

#### 1 million coros


| Mode | Threads | Total time |
| --- | --- | --- |
| TonIO yield | 1 | 742.544ms |
| TonIO async | 1 | 1117.031ms |
| TonIO yield | 2 | 1068.347ms |
| TonIO async | 2 | 1086.841ms |
| TonIO yield | 4 | 985.668ms |
| TonIO async | 4 | 1097.441ms |
| TonIO yield | 8 | 1933.909ms |
| TonIO async | 8 | 1349.145ms |

#### Sockets


| Mode | Threads | Throughput (10KB) |
| --- | --- | --- |
| TonIO yield | 1 | 132795.1 |
| TonIO async | 1 | 96793.8 |
| TonIO yield | 2 | 142084.5 |
| TonIO async | 2 | 157012.3 |
| TonIO yield | 4 | 130808.0 |
| TonIO async | 4 | 138275.8 |
| TonIO yield | 8 | 98894.0 |
| TonIO async | 8 | 125243.8 |
