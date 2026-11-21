Zbiór: tabela/kolekcja `papers_100`. Czasy: mediana z 5 uruchomień po rozgrzewce.

| zapytanie | wyniki LIKE | wyniki FTS (SQL) | numFound Solr | LIKE exec [ms] | FTS exec [ms] | FTS klient [ms] | Solr QTime [ms] | Solr klient [ms] | Solr QTime cache=false [ms] | Solr klient cache=false [ms] |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Q1: słowo w dowolnej formie: simulate (simulated, simulates, simulating, simulation…) | 24333 | 119222 | 119255 | 4754.939 | 120.067 | 112.627 | 0.0 | 3.895 | 6.0 | 8.503 |
| Q2: fraza "dark matter" (słowa obok siebie, w tej kolejności) | 14655 | 14955 | 15025 | 4629.645 | 66.185 | 69.83 | 0.0 | 3.5 | 3.0 | 6.433 |
| Q3: galaxy AND (cluster OR merger) AND NOT simulation | 7259 | 8887 | 8918 | 4856.824 | 15.126 | 15.694 | 0.0 | 3.091 | 4.0 | 7.223 |
| Q1+fq: Q1 z filtrem: archive=astro-ph, lata 2010–2020 | 2138 | 9447 | 9449 | 400.616 | 98.726 | 98.189 | 0.0 | 4.093 | 2.0 | 6.043 |
