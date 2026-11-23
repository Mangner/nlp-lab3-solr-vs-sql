Zbiór: tabela/kolekcja `papers_100`. Czasy: mediana z 5 uruchomień po rozgrzewce.

| zapytanie | wyniki LIKE | wyniki FTS (SQL) | numFound Solr | LIKE exec [ms] | FTS exec [ms] | FTS klient [ms] | Solr QTime [ms] | Solr klient [ms] | Solr QTime cache=false [ms] | Solr klient cache=false [ms] |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Q1: słowo w dowolnej formie: simulate (simulated, simulates, simulating, simulation…) | 24333 | 119222 | 119255 | 4631.713 | 99.07 | 95.689 | 2.0 | 8.305 | 14.0 | 20.391 |
| Q2: fraza "dark matter" (słowa obok siebie, w tej kolejności) | 14655 | 14955 | 15025 | 4398.25 | 64.652 | 64.115 | 1.0 | 5.422 | 5.0 | 10.131 |
| Q3: galaxy AND (cluster OR merger) AND NOT simulation | 7259 | 8887 | 8918 | 4653.637 | 15.16 | 16.372 | 1.0 | 5.77 | 12.0 | 17.362 |
| Q1+fq: Q1 z filtrem: archive=astro-ph, lata 2010–2020 | 2138 | 9447 | 9449 | 370.941 | 83.301 | 85.348 | 1.0 | 4.965 | 5.0 | 9.292 |
