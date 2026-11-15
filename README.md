# Prețuri pentru comparatorul bigmarket.ro

Roboții care citesc, după codul de bare, prețul aceluiași produs la alte magazine online din România.
Aici sunt doar codurile de bare ale produselor (`coduri.txt`, publice oricum pe bigmarket.ro) și prețurile publice găsite.

- `robot/auchan.py`: catalogul public Auchan, după codul de bare (permis de robots.txt-ul lor), la 3 ore.
- `robot/cautare.py`: o singură căutare pe produs (Serper, plafon 2.400), apoi reverificare gratuită a paginilor găsite, la 6 ore,
  doar unde robots.txt-ul magazinului permite și doar dacă pagina are același cod de bare.
- `preturi.json`: toate prețurile într-un singur fișier; îl citește serverul bigmarket.ro.

Un preț dispărut (produsul nu mai e pe pagină / în stoc) rămâne cu data la care l-am văzut („vazut”), cel mult 30 de zile.
