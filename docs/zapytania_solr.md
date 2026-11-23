# Zapytania Solra (poziom 3.0) — URL-e do wklejenia w przeglądarkę

Kolekcja: `papers_100`. Admin UI → Query: wklej `q`, `fq`, `fl`, `sort`, `rows`. Ten plik jest generowany przez `python -m lab3.level3`.

## Q1 — słowo w dowolnej formie: simulate (simulated, simulates, simulating, simulation…)

- numFound: **119255**, QTime (mediana): 2.0 ms
- [http://localhost:8983/solr/papers_100/select?q=text_all%3Asimulate&fl=id%2Ctitle%2Cprimary_category%2Carchive%2Cyear%2Cscore&sort=score+desc%2C+id+asc&rows=10&wt=json](http://localhost:8983/solr/papers_100/select?q=text_all%3Asimulate&fl=id%2Ctitle%2Cprimary_category%2Carchive%2Cyear%2Cscore&sort=score+desc%2C+id+asc&rows=10&wt=json)

## Q2 — fraza "dark matter" (słowa obok siebie, w tej kolejności)

- numFound: **15025**, QTime (mediana): 1.0 ms
- [http://localhost:8983/solr/papers_100/select?q=text_all%3A%22dark+matter%22&fl=id%2Ctitle%2Cprimary_category%2Carchive%2Cyear%2Cscore&sort=score+desc%2C+id+asc&rows=10&wt=json](http://localhost:8983/solr/papers_100/select?q=text_all%3A%22dark+matter%22&fl=id%2Ctitle%2Cprimary_category%2Carchive%2Cyear%2Cscore&sort=score+desc%2C+id+asc&rows=10&wt=json)

## Q3 — galaxy AND (cluster OR merger) AND NOT simulation

- numFound: **8918**, QTime (mediana): 1.0 ms
- [http://localhost:8983/solr/papers_100/select?q=text_all%3Agalaxy+AND+%28text_all%3Acluster+OR+text_all%3Amerger%29+AND+NOT+text_all%3Asimulation&fl=id%2Ctitle%2Cprimary_category%2Carchive%2Cyear%2Cscore&sort=score+desc%2C+id+asc&rows=10&wt=json](http://localhost:8983/solr/papers_100/select?q=text_all%3Agalaxy+AND+%28text_all%3Acluster+OR+text_all%3Amerger%29+AND+NOT+text_all%3Asimulation&fl=id%2Ctitle%2Cprimary_category%2Carchive%2Cyear%2Cscore&sort=score+desc%2C+id+asc&rows=10&wt=json)

## Q1+fq — Q1 z filtrem: archive=astro-ph, lata 2010–2020

- numFound: **9449**, QTime (mediana): 1.0 ms
- [http://localhost:8983/solr/papers_100/select?q=text_all%3Asimulate&fl=id%2Ctitle%2Cprimary_category%2Carchive%2Cyear%2Cscore&sort=score+desc%2C+id+asc&rows=10&fq=archive%3Aastro-ph&fq=year%3A%5B2010+TO+2020%5D&wt=json](http://localhost:8983/solr/papers_100/select?q=text_all%3Asimulate&fl=id%2Ctitle%2Cprimary_category%2Carchive%2Cyear%2Cscore&sort=score+desc%2C+id+asc&rows=10&fq=archive%3Aastro-ph&fq=year%3A%5B2010+TO+2020%5D&wt=json)
