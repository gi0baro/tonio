# TonIO benchmarks

Run at: Mon 02 Mar 2026, 00:00    
Environment: AMD Ryzen 7 5700X @ Gentoo Linux 6.18.12 (CPUs: 16)    
Python version: 3.14    
TonIO version: 0.2.0    

### Running 1 million coroutines

Time to run 1 million coroutines (lower is better).


| Runtime | Creation time | Exec time | Total time |
| --- | --- | --- | --- |
| TonIO yield | 84.287ms | 711.945ms | 796.232ms (3.68x) |
| TonIO async | 74.761ms | 1305.929ms | 1380.691ms (2.12x) |
| TonIO yield (context) | 86.173ms | 793.97ms | 880.143ms (3.33x) |
| TonIO async (context) | 47.755ms | 1403.072ms | 1450.826ms (2.02x) |
| AsyncIO | 39.245ms | 2888.057ms | 2927.302ms (1.0x) |
| Trio | 2213.043ms | 5151.536ms | 7364.579ms (0.4x) |
| TinyIO | 71.379ms | 3213.608ms | 3284.987ms (0.89x) |

### Sockets

TCP echo server with raw sockets comparison using 1KB, 10KB and 100KB messages.


| Runtime | Throughput (1KB) | Throughput (10KB) | Throughput (100KB) |
| --- | --- | --- | --- |
| TonIO yield | 134927.2 (2.49x) | 119890.6 (2.48x) | 46333.5 (1.66x) | 
| TonIO async | 110508.0 (2.04x) | 92505.3 (1.91x) | 39763.7 (1.43x) | 
| TonIO yield (context) | 133842.9 (2.47x) | 120397.6 (2.49x) | 46026.5 (1.65x) | 
| TonIO async (context) | 111690.6 (2.06x) | 93650.9 (1.93x) | 40585.3 (1.46x) | 
| AsyncIO | 54091.9 (1.0x) | 48418.4 (1.0x) | 27880.9 (1.0x) | 
| Trio | 78356.9 (1.45x) | 68559.0 (1.42x) | 33237.9 (1.19x) | 

#### 1KB details

| Runtime | Total requests | Throughput | Mean latency | 99p latency | Latency stdev |
| --- | --- | --- | --- | --- | --- |
| TonIO yield | 1349272 | 134927.2 (2.49x) | 0.03ms | 0.049ms | 0.007 |
| TonIO async | 1105080 | 110508.0 (2.04x) | 0.033ms | 0.05ms | 0.006 |
| TonIO yield (context) | 1338429 | 133842.9 (2.47x) | 0.03ms | 0.049ms | 0.007 |
| TonIO async (context) | 1116906 | 111690.6 (2.06x) | 0.033ms | 0.05ms | 0.005 |
| AsyncIO | 540919 | 54091.9 (1.0x) | 0.071ms | 0.089ms | 0.004 |
| Trio | 783569 | 78356.9 (1.45x) | 0.05ms | 0.077ms | 0.009 |


#### 10KB details

| Runtime | Total requests | Throughput | Mean latency | 99p latency | Latency stdev |
| --- | --- | --- | --- | --- | --- |
| TonIO yield | 1198906 | 119890.6 (2.48x) | 0.032ms | 0.054ms | 0.005 |
| TonIO async | 925053 | 92505.3 (1.91x) | 0.041ms | 0.059ms | 0.007 |
| TonIO yield (context) | 1203976 | 120397.6 (2.49x) | 0.032ms | 0.055ms | 0.005 |
| TonIO async (context) | 936509 | 93650.9 (1.93x) | 0.041ms | 0.058ms | 0.003 |
| AsyncIO | 484184 | 48418.4 (1.0x) | 0.081ms | 0.098ms | 0.004 |
| Trio | 685590 | 68559.0 (1.42x) | 0.056ms | 0.086ms | 0.011 |


#### 100KB details

| Runtime | Total requests | Throughput | Mean latency | 99p latency | Latency stdev |
| --- | --- | --- | --- | --- | --- |
| TonIO yield | 463335 | 46333.5 (1.66x) | 0.084ms | 0.147ms | 0.014 |
| TonIO async | 397637 | 39763.7 (1.43x) | 0.099ms | 0.118ms | 0.005 |
| TonIO yield (context) | 460265 | 46026.5 (1.65x) | 0.085ms | 0.147ms | 0.013 |
| TonIO async (context) | 405853 | 40585.3 (1.46x) | 0.096ms | 0.124ms | 0.009 |
| AsyncIO | 278809 | 27880.9 (1.0x) | 0.141ms | 0.177ms | 0.01 |
| Trio | 332379 | 33237.9 (1.19x) | 0.118ms | 0.169ms | 0.023 |


### Concurrency

#### 1 million coros


| Mode | Threads | Total time |
| --- | --- | --- |
| TonIO yield | 1 | 747.627ms |
| TonIO async | 1 | 1375.505ms |
| TonIO yield | 2 | 1130.779ms |
| TonIO async | 2 | 1333.086ms |
| TonIO yield | 4 | 1102.704ms |
| TonIO async | 4 | 1345.077ms |
| TonIO yield | 8 | 2520.575ms |
| TonIO async | 8 | 1452.933ms |

#### Sockets


| Mode | Threads | Throughput (10KB) |
| --- | --- | --- |
| TonIO yield | 1 | 118823.2 |
| TonIO async | 1 | 94315.7 |
| TonIO yield | 2 | 131797.5 |
| TonIO async | 2 | 140311.3 |
| TonIO yield | 4 | 124154.0 |
| TonIO async | 4 | 130663.1 |
| TonIO yield | 8 | 94404.5 |
| TonIO async | 8 | 118476.3 |
