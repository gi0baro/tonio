# TonIO benchmarks

Run at: Mon 02 Mar 2026, 17:42    
Environment: AMD Ryzen 7 5700X @ Gentoo Linux 6.12.74 (CPUs: 16)    
Python version: 3.14    
TonIO version: 0.2.0    

### Running 1 million coroutines

Time to run 1 million coroutines (lower is better).


| Runtime | Creation time | Exec time | Total time |
| --- | --- | --- | --- |
| TonIO yield | 79.85ms | 681.017ms | 760.866ms (3.88x) |
| TonIO async | 89.868ms | 1020.063ms | 1109.931ms (2.66x) |
| TonIO yield (context) | 100.07ms | 758.056ms | 858.126ms (3.44x) |
| TonIO async (context) | 83.284ms | 1180.467ms | 1263.751ms (2.33x) |
| AsyncIO | 39.291ms | 2911.148ms | 2950.44ms (1.0x) |
| Trio | 2278.832ms | 5351.983ms | 7630.816ms (0.39x) |
| TinyIO | 72.836ms | 3232.209ms | 3305.045ms (0.89x) |

### Sockets

TCP echo server with raw sockets comparison using 1KB, 10KB and 100KB messages.


| Runtime | Throughput (1KB) | Throughput (10KB) | Throughput (100KB) |
| --- | --- | --- | --- |
| TonIO yield | 152395.6 (2.79x) | 131655.5 (2.84x) | 47754.5 (1.71x) | 
| TonIO async | 113405.0 (2.07x) | 94102.9 (2.03x) | 39223.0 (1.4x) | 
| TonIO yield (context) | 150132.9 (2.74x) | 137143.8 (2.96x) | 47562.2 (1.7x) | 
| TonIO async (context) | 113960.5 (2.08x) | 94630.5 (2.04x) | 38916.8 (1.39x) | 
| AsyncIO | 54696.3 (1.0x) | 46362.3 (1.0x) | 27965.9 (1.0x) | 
| Trio | 77584.4 (1.42x) | 66580.2 (1.44x) | 33858.7 (1.21x) | 

#### 1KB details

| Runtime | Total requests | Throughput | Mean latency | 99p latency | Latency stdev |
| --- | --- | --- | --- | --- | --- |
| TonIO yield | 1523956 | 152395.6 (2.79x) | 0.023ms | 0.046ms | 0.006 |
| TonIO async | 1134050 | 113405.0 (2.07x) | 0.032ms | 0.049ms | 0.005 |
| TonIO yield (context) | 1501329 | 150132.9 (2.74x) | 0.024ms | 0.046ms | 0.006 |
| TonIO async (context) | 1139605 | 113960.5 (2.08x) | 0.032ms | 0.049ms | 0.004 |
| AsyncIO | 546963 | 54696.3 (1.0x) | 0.071ms | 0.087ms | 0.003 |
| Trio | 775844 | 77584.4 (1.42x) | 0.05ms | 0.078ms | 0.011 |


#### 10KB details

| Runtime | Total requests | Throughput | Mean latency | 99p latency | Latency stdev |
| --- | --- | --- | --- | --- | --- |
| TonIO yield | 1316555 | 131655.5 (2.84x) | 0.03ms | 0.047ms | 0.003 |
| TonIO async | 941029 | 94102.9 (2.03x) | 0.04ms | 0.055ms | 0.002 |
| TonIO yield (context) | 1371438 | 137143.8 (2.96x) | 0.031ms | 0.047ms | 0.003 |
| TonIO async (context) | 946305 | 94630.5 (2.04x) | 0.04ms | 0.055ms | 0.002 |
| AsyncIO | 463623 | 46362.3 (1.0x) | 0.085ms | 0.102ms | 0.006 |
| Trio | 665802 | 66580.2 (1.44x) | 0.059ms | 0.089ms | 0.012 |


#### 100KB details

| Runtime | Total requests | Throughput | Mean latency | 99p latency | Latency stdev |
| --- | --- | --- | --- | --- | --- |
| TonIO yield | 477545 | 47754.5 (1.71x) | 0.082ms | 0.135ms | 0.009 |
| TonIO async | 392230 | 39223.0 (1.4x) | 0.1ms | 0.119ms | 0.004 |
| TonIO yield (context) | 475622 | 47562.2 (1.7x) | 0.082ms | 0.142ms | 0.012 |
| TonIO async (context) | 389168 | 38916.8 (1.39x) | 0.101ms | 0.12ms | 0.006 |
| AsyncIO | 279659 | 27965.9 (1.0x) | 0.141ms | 0.161ms | 0.006 |
| Trio | 338587 | 33858.7 (1.21x) | 0.116ms | 0.168ms | 0.022 |


### Concurrency

#### 1 million coros


| Mode | Threads | Total time |
| --- | --- | --- |
| TonIO yield | 1 | 724.874ms |
| TonIO async | 1 | 1114.689ms |
| TonIO yield | 2 | 1070.915ms |
| TonIO async | 2 | 1161.46ms |
| TonIO yield | 4 | 963.598ms |
| TonIO async | 4 | 1130.329ms |
| TonIO yield | 8 | 1900.294ms |
| TonIO async | 8 | 1308.071ms |

#### Sockets


| Mode | Threads | Throughput (10KB) |
| --- | --- | --- |
| TonIO yield | 1 | 134018.5 |
| TonIO async | 1 | 92041.8 |
| TonIO yield | 2 | 138206.3 |
| TonIO async | 2 | 150216.9 |
| TonIO yield | 4 | 127086.9 |
| TonIO async | 4 | 138142.6 |
| TonIO yield | 8 | 98849.1 |
| TonIO async | 8 | 123825.6 |
