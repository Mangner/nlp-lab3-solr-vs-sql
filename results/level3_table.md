Zbiór: tabela/kolekcja `papers_100`. Czasy: mediana z 5 uruchomień po rozgrzewce.

| zapytanie | wyniki LIKE | wyniki FTS (SQL) | numFound Solr | LIKE exec [ms] | FTS exec [ms] | FTS klient [ms] | Solr QTime [ms] | Solr klient [ms] |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Q1: słowo w dowolnej formie: simulate (simulated, simulates, simulating, simulation…) | 24333 | 119222 | 119255 | 4665.825 | 124.363 | 108.398 | 1.0 | 17.021 |
| Q2: fraza "dark matter" (słowa obok siebie, w tej kolejności) | 14655 | 14955 | 15025 | 4570.948 | 65.576 | 67.87 | 1.0 | 15.373 |
| Q3: galaxy AND (cluster OR merger) AND NOT simulation | 7259 | 8887 | 8918 | 4840.047 | 14.909 | 15.471 | 1.0 | 8.717 |
| Q1+fq: Q1 z filtrem: archive=astro-ph, lata 2010–2020 | 2138 | 9447 | 9449 | 405.466 | 88.873 | 89.856 | 1.0 | 20.236 |
