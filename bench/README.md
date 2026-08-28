# TonIO benchmarks

Run at: Fri 28 Aug 2026, 11:50    
Environment: AMD Ryzen 7 5700X @ Gentoo Linux 6.18.43 (CPUs: 16)    
Python version: 3.14    
TonIO version: 0.9.12    

### Running 1 million coroutines

Time to run 1 million coroutines (lower is better).


| Runtime | Creation time | Exec time | Total time | Relative performance |
| --- | --- | --- | --- | --- |
| TonIO yield | 112.499ms | 433.564ms | 546.063ms | 5.37x |
| TonIO async | 115.343ms | 807.16ms | 922.503ms | 3.18x |
| TonIO yield (context) | 99.181ms | 569.212ms | 668.392ms | 4.39x |
| TonIO async (context) | 57.497ms | 959.479ms | 1016.975ms | 2.88x |
| AsyncIO | 41.578ms | 2891.766ms | 2933.344ms | 1.0x |
| Trio | 2206.94ms | 5329.275ms | 7536.215ms | 0.39x |
| TinyIO | 71.828ms | 3359.866ms | 3431.694ms | 0.85x |

### Sockets

TCP echo server with raw sockets comparison using 1KB, 10KB and 100KB messages.


| Runtime | Throughput (1KB) | Throughput (10KB) | Throughput (100KB) |
| --- | --- | --- | --- |
| TonIO yield | 125611.0 (2.34x) | 105572.6 (2.21x) | 42750.6 (1.53x) | 
| TonIO async | 131035.4 (2.44x) | 106140.4 (2.22x) | 42046.9 (1.51x) | 
| TonIO yield (context) | 125403.7 (2.33x) | 104712.3 (2.19x) | 43059.3 (1.54x) | 
| TonIO async (context) | 128785.0 (2.4x) | 108100.8 (2.27x) | 42703.7 (1.53x) | 
| AsyncIO | 53716.3 (1.0x) | 47711.2 (1.0x) | 27910.4 (1.0x) | 
| Trio | 76594.4 (1.43x) | 69090.5 (1.45x) | 32879.1 (1.18x) | 

#### 1KB details

| Runtime | Total requests | Throughput | Mean latency | 99p latency | Latency stdev |
| --- | --- | --- | --- | --- | --- |
| TonIO yield | 1256110 | 125611.0 (2.34x) | 0.03ms | 0.04ms | 0.002 |
| TonIO async | 1310354 | 131035.4 (2.44x) | 0.03ms | 0.04ms | 0.001 |
| TonIO yield (context) | 1254037 | 125403.7 (2.33x) | 0.03ms | 0.04ms | 0.001 |
| TonIO async (context) | 1287850 | 128785.0 (2.4x) | 0.03ms | 0.044ms | 0.002 |
| AsyncIO | 537163 | 53716.3 (1.0x) | 0.071ms | 0.089ms | 0.004 |
| Trio | 765944 | 76594.4 (1.43x) | 0.051ms | 0.079ms | 0.01 |


#### 10KB details

| Runtime | Total requests | Throughput | Mean latency | 99p latency | Latency stdev |
| --- | --- | --- | --- | --- | --- |
| TonIO yield | 1055726 | 105572.6 (2.21x) | 0.04ms | 0.05ms | 0.002 |
| TonIO async | 1061404 | 106140.4 (2.22x) | 0.037ms | 0.05ms | 0.005 |
| TonIO yield (context) | 1047123 | 104712.3 (2.19x) | 0.04ms | 0.05ms | 0.001 |
| TonIO async (context) | 1081008 | 108100.8 (2.27x) | 0.037ms | 0.05ms | 0.005 |
| AsyncIO | 477112 | 47711.2 (1.0x) | 0.081ms | 0.099ms | 0.004 |
| Trio | 690905 | 69090.5 (1.45x) | 0.056ms | 0.085ms | 0.011 |


#### 100KB details

| Runtime | Total requests | Throughput | Mean latency | 99p latency | Latency stdev |
| --- | --- | --- | --- | --- | --- |
| TonIO yield | 427506 | 42750.6 (1.53x) | 0.091ms | 0.11ms | 0.005 |
| TonIO async | 420469 | 42046.9 (1.51x) | 0.093ms | 0.113ms | 0.006 |
| TonIO yield (context) | 430593 | 43059.3 (1.54x) | 0.091ms | 0.11ms | 0.004 |
| TonIO async (context) | 427037 | 42703.7 (1.53x) | 0.092ms | 0.109ms | 0.005 |
| AsyncIO | 279104 | 27910.4 (1.0x) | 0.141ms | 0.16ms | 0.005 |
| Trio | 328791 | 32879.1 (1.18x) | 0.119ms | 0.169ms | 0.022 |


### Concurrency

#### 1 million coros


| Mode | Threads | Total time |
| --- | --- | --- |
| TonIO yield | 1 | 544.295ms |
| TonIO async | 1 | 917.023ms |
| TonIO yield | 2 | 647.375ms |
| TonIO async | 2 | 902.957ms |
| TonIO yield | 4 | 1005.149ms |
| TonIO async | 4 | 932.598ms |
| TonIO yield | 8 | 1180.3ms |
| TonIO async | 8 | 1100.478ms |

#### Sockets


| Mode | Threads | Throughput (10KB) |
| --- | --- | --- |
| TonIO yield | 1 | 104987.3 |
| TonIO async | 1 | 105916.4 |
| TonIO yield | 2 | 179482.8 |
| TonIO async | 2 | 187259.3 |
| TonIO yield | 4 | 254578.6 |
| TonIO async | 4 | 264705.8 |
| TonIO yield | 8 | 349393.7 |
| TonIO async | 8 | 364658.1 |
