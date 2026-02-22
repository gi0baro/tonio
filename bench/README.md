# TonIO benchmarks

Run at: Sun 22 Feb 2026, 14:02    
Environment: AMD Ryzen 7 5700X @ Gentoo Linux 6.12.68 (CPUs: 16)    
Python version: 3.14    
TonIO version: 0.1.0    

### Running 1 million coroutines

Time to run 1 million coroutines (lower is better).


| Runtime | Creation time | Exec time | Total time |
| --- | --- | --- | --- |
| TonIO yield | 66.339ms | 1133.059ms | 1199.398ms (2.46x) |
| TonIO async | 50.329ms | 1716.066ms | 1766.395ms (1.67x) |
| TonIO yield (context) | 72.692ms | 1233.951ms | 1306.642ms (2.26x) |
| TonIO async (context) | 50.188ms | 1857.882ms | 1908.07ms (1.55x) |
| AsyncIO | 41.69ms | 2914.393ms | 2956.082ms (1.0x) |
| Trio | 2885.391ms | 4703.729ms | 7589.119ms (0.39x) |
| TinyIO | 74.813ms | 3236.883ms | 3311.696ms (0.89x) |

### Sockets

TCP echo server with raw sockets comparison using 1KB, 10KB and 100KB messages.


| Runtime | Throughput (1KB) | Throughput (10KB) | Throughput (100KB) |
| --- | --- | --- | --- |
| TonIO yield | 147996.1 (2.76x) | 132782.2 (2.85x) | 46909.8 (1.73x) | 
| TonIO async | 108862.1 (2.03x) | 93342.6 (2.0x) | 41551.4 (1.53x) | 
| TonIO yield (context) | 154497.5 (2.88x) | 134092.0 (2.88x) | 46988.3 (1.73x) | 
| TonIO async (context) | 110634.7 (2.06x) | 91473.6 (1.96x) | 40717.1 (1.5x) | 
| AsyncIO | 53664.2 (1.0x) | 46630.9 (1.0x) | 27134.0 (1.0x) | 
| Trio | 81380.7 (1.52x) | 70101.7 (1.5x) | 34635.6 (1.28x) | 

#### 1KB details

| Runtime | Total requests | Throughput | Mean latency | 99p latency | Latency stdev |
| --- | --- | --- | --- | --- | --- |
| TonIO yield | 1479961 | 147996.1 (2.76x) | 0.024ms | 0.047ms | 0.006 |
| TonIO async | 1088621 | 108862.1 (2.03x) | 0.035ms | 0.05ms | 0.005 |
| TonIO yield (context) | 1544975 | 154497.5 (2.88x) | 0.023ms | 0.046ms | 0.006 |
| TonIO async (context) | 1106347 | 110634.7 (2.06x) | 0.035ms | 0.05ms | 0.005 |
| AsyncIO | 536642 | 53664.2 (1.0x) | 0.073ms | 0.092ms | 0.006 |
| Trio | 813807 | 81380.7 (1.52x) | 0.047ms | 0.071ms | 0.009 |


#### 10KB details

| Runtime | Total requests | Throughput | Mean latency | 99p latency | Latency stdev |
| --- | --- | --- | --- | --- | --- |
| TonIO yield | 1327822 | 132782.2 (2.85x) | 0.03ms | 0.047ms | 0.003 |
| TonIO async | 933426 | 93342.6 (2.0x) | 0.041ms | 0.058ms | 0.004 |
| TonIO yield (context) | 1340920 | 134092.0 (2.88x) | 0.03ms | 0.04ms | 0.002 |
| TonIO async (context) | 914736 | 91473.6 (1.96x) | 0.042ms | 0.059ms | 0.004 |
| AsyncIO | 466309 | 46630.9 (1.0x) | 0.085ms | 0.105ms | 0.006 |
| Trio | 701017 | 70101.7 (1.5x) | 0.055ms | 0.08ms | 0.01 |


#### 100KB details

| Runtime | Total requests | Throughput | Mean latency | 99p latency | Latency stdev |
| --- | --- | --- | --- | --- | --- |
| TonIO yield | 469098 | 46909.8 (1.73x) | 0.083ms | 0.109ms | 0.008 |
| TonIO async | 415514 | 41551.4 (1.53x) | 0.094ms | 0.113ms | 0.006 |
| TonIO yield (context) | 469883 | 46988.3 (1.73x) | 0.083ms | 0.108ms | 0.007 |
| TonIO async (context) | 407171 | 40717.1 (1.5x) | 0.097ms | 0.117ms | 0.007 |
| AsyncIO | 271340 | 27134.0 (1.0x) | 0.144ms | 0.169ms | 0.01 |
| Trio | 346356 | 34635.6 (1.28x) | 0.114ms | 0.163ms | 0.022 |


### Concurrency

#### 1 million coros


| Mode | Threads | Total time |
| --- | --- | --- |
| TonIO yield | 1 | 1171.784ms |
| TonIO async | 1 | 1766.377ms |
| TonIO yield | 2 | 1113.641ms |
| TonIO async | 2 | 1482.32ms |
| TonIO yield | 4 | 2236.277ms |
| TonIO async | 4 | 1635.187ms |
| TonIO yield | 8 | 3625.067ms |
| TonIO async | 8 | 2514.29ms |

#### Sockets


| Mode | Threads | Throughput (10KB) |
| --- | --- | --- |
| TonIO yield | 1 | 132858.0 |
| TonIO async | 1 | 92223.7 |
| TonIO yield | 2 | 135034.3 |
| TonIO async | 2 | 143182.5 |
| TonIO yield | 4 | 127375.0 |
| TonIO async | 4 | 135086.5 |
| TonIO yield | 8 | 95125.2 |
| TonIO async | 8 | 120261.7 |
