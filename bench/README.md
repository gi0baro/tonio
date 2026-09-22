# TonIO benchmarks

Run at: Tue 22 Sep 2026, 19:57    
Environment: AMD Ryzen 7 5700X @ Gentoo Linux 6.18.48 (CPUs: 16)    
Python version: 3.14    
TonIO version: 0.10.0    

### Running 1 million coroutines

Time to run 1 million coroutines (lower is better).


| Runtime | Creation time | Exec time | Total time | Relative performance |
| --- | --- | --- | --- | --- |
| TonIO yield | 76.496ms | 398.708ms | 475.204ms | 6.15x |
| TonIO async | 52.922ms | 747.758ms | 800.68ms | 3.65x |
| TonIO yield (context) | 103.685ms | 528.763ms | 632.448ms | 4.62x |
| TonIO async (context) | 105.685ms | 841.486ms | 947.171ms | 3.09x |
| AsyncIO | 39.908ms | 2882.912ms | 2922.82ms | 1.0x |
| Trio | 2942.011ms | 5284.408ms | 8226.418ms | 0.36x |
| TinyIO | 70.535ms | 3386.907ms | 3457.443ms | 0.85x |

### Sockets

TCP echo server with raw sockets comparison using 1KB, 10KB and 100KB messages.


| Runtime | Throughput (1KB) | Throughput (10KB) | Throughput (100KB) |
| --- | --- | --- | --- |
| TonIO yield | 127607.9 (2.36x) | 107222.9 (2.3x) | 41935.8 (1.54x) | 
| TonIO async | 134501.9 (2.49x) | 111889.0 (2.4x) | 41631.4 (1.53x) | 
| TonIO yield (context) | 126826.5 (2.35x) | 106694.7 (2.29x) | 41108.6 (1.51x) | 
| TonIO async (context) | 133016.5 (2.46x) | 109663.4 (2.35x) | 42794.2 (1.57x) | 
| AsyncIO | 53995.3 (1.0x) | 46621.3 (1.0x) | 27204.7 (1.0x) | 
| Trio | 80128.7 (1.48x) | 69221.3 (1.48x) | 34299.1 (1.26x) | 

#### 1KB details

| Runtime | Total requests | Throughput | Mean latency | 99p latency | Latency stdev |
| --- | --- | --- | --- | --- | --- |
| TonIO yield | 1276079 | 127607.9 (2.36x) | 0.03ms | 0.041ms | 0.002 |
| TonIO async | 1345019 | 134501.9 (2.49x) | 0.03ms | 0.04ms | 0.001 |
| TonIO yield (context) | 1268265 | 126826.5 (2.35x) | 0.03ms | 0.04ms | 0.001 |
| TonIO async (context) | 1330165 | 133016.5 (2.46x) | 0.03ms | 0.04ms | 0.001 |
| AsyncIO | 539953 | 53995.3 (1.0x) | 0.071ms | 0.089ms | 0.004 |
| Trio | 801287 | 80128.7 (1.48x) | 0.048ms | 0.074ms | 0.01 |


#### 10KB details

| Runtime | Total requests | Throughput | Mean latency | 99p latency | Latency stdev |
| --- | --- | --- | --- | --- | --- |
| TonIO yield | 1072229 | 107222.9 (2.3x) | 0.038ms | 0.05ms | 0.007 |
| TonIO async | 1118890 | 111889.0 (2.4x) | 0.033ms | 0.049ms | 0.005 |
| TonIO yield (context) | 1066947 | 106694.7 (2.29x) | 0.039ms | 0.05ms | 0.003 |
| TonIO async (context) | 1096634 | 109663.4 (2.35x) | 0.034ms | 0.05ms | 0.006 |
| AsyncIO | 466213 | 46621.3 (1.0x) | 0.085ms | 0.103ms | 0.006 |
| Trio | 692213 | 69221.3 (1.48x) | 0.056ms | 0.084ms | 0.01 |


#### 100KB details

| Runtime | Total requests | Throughput | Mean latency | 99p latency | Latency stdev |
| --- | --- | --- | --- | --- | --- |
| TonIO yield | 419358 | 41935.8 (1.54x) | 0.093ms | 0.11ms | 0.006 |
| TonIO async | 416314 | 41631.4 (1.53x) | 0.093ms | 0.114ms | 0.006 |
| TonIO yield (context) | 411086 | 41108.6 (1.51x) | 0.095ms | 0.115ms | 0.006 |
| TonIO async (context) | 427942 | 42794.2 (1.57x) | 0.092ms | 0.115ms | 0.006 |
| AsyncIO | 272047 | 27204.7 (1.0x) | 0.145ms | 0.169ms | 0.008 |
| Trio | 342991 | 34299.1 (1.26x) | 0.114ms | 0.162ms | 0.022 |


### Concurrency

#### 1 million coros


| Mode | Threads | Total time |
| --- | --- | --- |
| TonIO yield | 1 | 479.075ms |
| TonIO async | 1 | 801.848ms |
| TonIO yield | 2 | 752.644ms |
| TonIO async | 2 | 814.24ms |
| TonIO yield | 4 | 936.607ms |
| TonIO async | 4 | 824.758ms |
| TonIO yield | 8 | 1090.656ms |
| TonIO async | 8 | 965.765ms |

#### Sockets


| Mode | Threads | Throughput (10KB) |
| --- | --- | --- |
| TonIO yield | 1 | 103847.4 |
| TonIO async | 1 | 108396.4 |
| TonIO yield | 2 | 175896.8 |
| TonIO async | 2 | 193676.5 |
| TonIO yield | 4 | 260271.3 |
| TonIO async | 4 | 270202.6 |
| TonIO yield | 8 | 355224.0 |
| TonIO async | 8 | 360090.0 |
