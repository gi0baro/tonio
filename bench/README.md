# TonIO benchmarks

Run at: Sun 01 Mar 2026, 19:07    
Environment: AMD Ryzen 7 5700X @ Gentoo Linux 6.18.12 (CPUs: 16)    
Python version: 3.14    
TonIO version: 0.2.0    

### Running 1 million coroutines

Time to run 1 million coroutines (lower is better).


| Runtime | Creation time | Exec time | Total time |
| --- | --- | --- | --- |
| TonIO yield | 86.091ms | 802.331ms | 888.422ms (3.29x) |
| TonIO async | 72.743ms | 1406.071ms | 1478.814ms (1.98x) |
| TonIO yield (context) | 89.392ms | 873.08ms | 962.472ms (3.04x) |
| TonIO async (context) | 51.994ms | 1509.89ms | 1561.883ms (1.87x) |
| AsyncIO | 38.979ms | 2887.197ms | 2926.177ms (1.0x) |
| Trio | 2222.672ms | 5306.105ms | 7528.778ms (0.39x) |
| TinyIO | 68.521ms | 3219.516ms | 3288.037ms (0.89x) |

### Sockets

TCP echo server with raw sockets comparison using 1KB, 10KB and 100KB messages.


| Runtime | Throughput (1KB) | Throughput (10KB) | Throughput (100KB) |
| --- | --- | --- | --- |
| TonIO yield | 134467.8 (2.49x) | 118753.7 (2.44x) | 46287.3 (1.65x) | 
| TonIO async | 110811.1 (2.05x) | 93838.5 (1.93x) | 39486.2 (1.41x) | 
| TonIO yield (context) | 135560.0 (2.51x) | 119092.9 (2.44x) | 45435.7 (1.62x) | 
| TonIO async (context) | 107997.2 (2.0x) | 92145.2 (1.89x) | 39420.4 (1.41x) | 
| AsyncIO | 54101.7 (1.0x) | 48710.9 (1.0x) | 28007.7 (1.0x) | 
| Trio | 78559.1 (1.45x) | 69043.5 (1.42x) | 33727.8 (1.2x) | 

#### 1KB details

| Runtime | Total requests | Throughput | Mean latency | 99p latency | Latency stdev |
| --- | --- | --- | --- | --- | --- |
| TonIO yield | 1344678 | 134467.8 (2.49x) | 0.03ms | 0.049ms | 0.007 |
| TonIO async | 1108111 | 110811.1 (2.05x) | 0.033ms | 0.05ms | 0.005 |
| TonIO yield (context) | 1355600 | 135560.0 (2.51x) | 0.03ms | 0.049ms | 0.007 |
| TonIO async (context) | 1079972 | 107997.2 (2.0x) | 0.035ms | 0.05ms | 0.006 |
| AsyncIO | 541017 | 54101.7 (1.0x) | 0.071ms | 0.089ms | 0.004 |
| Trio | 785591 | 78559.1 (1.45x) | 0.05ms | 0.077ms | 0.01 |


#### 10KB details

| Runtime | Total requests | Throughput | Mean latency | 99p latency | Latency stdev |
| --- | --- | --- | --- | --- | --- |
| TonIO yield | 1187537 | 118753.7 (2.44x) | 0.032ms | 0.056ms | 0.005 |
| TonIO async | 938385 | 93838.5 (1.93x) | 0.041ms | 0.057ms | 0.003 |
| TonIO yield (context) | 1190929 | 119092.9 (2.44x) | 0.032ms | 0.056ms | 0.005 |
| TonIO async (context) | 921452 | 92145.2 (1.89x) | 0.041ms | 0.058ms | 0.003 |
| AsyncIO | 487109 | 48710.9 (1.0x) | 0.081ms | 0.098ms | 0.004 |
| Trio | 690435 | 69043.5 (1.42x) | 0.056ms | 0.085ms | 0.011 |


#### 100KB details

| Runtime | Total requests | Throughput | Mean latency | 99p latency | Latency stdev |
| --- | --- | --- | --- | --- | --- |
| TonIO yield | 462873 | 46287.3 (1.65x) | 0.084ms | 0.144ms | 0.012 |
| TonIO async | 394862 | 39486.2 (1.41x) | 0.099ms | 0.12ms | 0.006 |
| TonIO yield (context) | 454357 | 45435.7 (1.62x) | 0.086ms | 0.147ms | 0.012 |
| TonIO async (context) | 394204 | 39420.4 (1.41x) | 0.1ms | 0.128ms | 0.006 |
| AsyncIO | 280077 | 28007.7 (1.0x) | 0.141ms | 0.171ms | 0.007 |
| Trio | 337278 | 33727.8 (1.2x) | 0.116ms | 0.167ms | 0.022 |


### Concurrency

#### 1 million coros


| Mode | Threads | Total time |
| --- | --- | --- |
| TonIO yield | 1 | 839.993ms |
| TonIO async | 1 | 1476.001ms |
| TonIO yield | 2 | 1172.24ms |
| TonIO async | 2 | 1399.748ms |
| TonIO yield | 4 | 1131.823ms |
| TonIO async | 4 | 1354.793ms |
| TonIO yield | 8 | 2471.506ms |
| TonIO async | 8 | 1282.127ms |

#### Sockets


| Mode | Threads | Throughput (10KB) |
| --- | --- | --- |
| TonIO yield | 1 | 119751.7 |
| TonIO async | 1 | 92655.5 |
| TonIO yield | 2 | 131178.7 |
| TonIO async | 2 | 142258.6 |
| TonIO yield | 4 | 124867.1 |
| TonIO async | 4 | 129730.3 |
| TonIO yield | 8 | 94934.3 |
| TonIO async | 8 | 118206.2 |
