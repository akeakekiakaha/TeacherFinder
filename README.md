# Teacher Finder · ZS1

Wyszukiwarka planowych zajęć nauczycieli, sal i klas na podstawie publicznie opublikowanych planów ZS1.

## Funkcje

- wyszukiwanie po kodzie nauczyciela, sali i oddziale;
- widok wyników z dniem, numerem lekcji, godziną, przedmiotem, salą i klasą;
- automatyczne wykrywanie oddziałów.
- pobieranie zmian z [oficjalnej strony ZS1](https://www.zs-1.edu.pl/index.php/plan-lekcji/zmiany-do-planu);
- wyświetlanie zastępstw i odwołań tylko w dniu wskazanym w zmianie, bez modyfikowania oryginalnych lekcji.

Importer zapisuje podstawowy plan w `lessons`, a ogłoszenia ze zmianami osobno w `changes`. Zachowuje oryginalny tekst każdego ogłoszenia; lekcje z zastępstwem są pokazywane jako skreślony plan i oznaczona zamiana, a odwołane lekcje jako skreślony plan bez nowego wpisu. Ogłoszenie o zwolnieniu do domu jest wyświetlane osobno jako zwykły tekst, bez przekreślenia; samo przekreślenie dotyczy tylko odwołanych lekcji. W widoku nauczyciela zastępstwo pokazuje aktualnego nauczyciela i salę bez nowego przedmiotu, a anulowane zajęcia nie są liczone jako jego obecність. W widoku sali zastępstwo pokazuje zarówno planowanego, jak i aktualnego nauczyciela; widok klasy zachowuje pełne informacje o zmianie. Zmiany dotyczące konkretnej grupy są stosowane wyłącznie do pasującej grupy. Synchronizacja obu źródeł odbywa się przez `python scripts/import_plans.py`.

Zastępstwo wyświetla nazwisko nauczyciela w formie podanej w ogłoszeniu. W `app.js` można uzupełnić `TEACHER_CODE_BY_SURNAME` w formacie `"Nazwisko": "XX"`, aby wyszukiwanie zastępstwa działało również po dwuliterowym kodzie z planu. Słownik jest na razie pusty, aby nie przypisywać kodów bez potwierdzonego źródła.

Wyszukiwanie nauczyciela po inicjałach może być niedokładne, ponieważ nie ma pełnego przypisania nazwisk nauczycieli do skrótów użytych w planach.

W wyszukiwaniu nauczyciela zastępstwo oznacza pierwotnego nauczyciela jako nieobecnego, bez wyświetlania danych zastępcy. Gdy zmienia się tylko sala, widok nauczyciela pokazuje bieżącą salę.

Wyniki widoku nauczyciela dla zastępstwa pokazują pierwotnego nauczyciela z oznaczeniem „Nieobecny”; nazwisko zastępcy, nowe zajęcia i tekst ogłoszenia nie są tam wyświetlane.

Wyniki można przełączyć z listy na tygodniową tabelę: wiersze pokazują numer i godzinę lekcji, a kolumny dni tygodnia. W widoku klasy zastępstwo jest wyróżnione bursztynowym kolorem, a podpowiedź pokazuje pierwotny plan; odwołane lekcje pozostają przekreślone. W widoku nauczyciela przekreślone są nieobecności, zaś zmiany sal pokazują bieżącą salę; w widoku sali aktualna obsada jest wyróżniona bursztynowym kolorem, a podpowiedź informuje o zastępstwie lub zmianie sali, bez pokazywania pierwotnego planu klasy.

W wynikach sali przeniesione zajęcia pojawiają się tylko w aktualnej sali. Podpowiedź pokazuje nauczyciela, który jest teraz w sali, oraz informuje, czy zastąpił planowego nauczyciela w tej sali, czy sala była wolna.

## Publikacja w GitHub Pages

GitHub Pages udostępnia aplikację jako statyczną stronę. Po jednorazowym włączeniu publikacji użytkownikom wystarczy otworzyć udostępniony adres — nie trzeba instalować ani uruchamiać projektu lokalnie. W repozytorium otwórz **Settings → Pages**, wybierz publikację z domyślnej gałęzi (np. `main`) i folderu `/(root)`. Pliki `index.html`, `app.js`, `styles.css` i `data/lessons.json` muszą pozostać w repozytorium pod tymi ścieżkami.

Strona korzysta z opublikowanego pliku `data/lessons.json`. W niedzielę o 20:00 czasu warszawskiego GitHub Actions pobiera plan na nadchodzący tydzień i rozpoczyna nowy zestaw zmian. Od poniedziałku do piątku o 20:00 pobierane są kolejne ogłoszenia; zmiany z wcześniejszych dni bieżącego tygodnia pozostają zapisane. W następną niedzielę poprzedni zestaw jest zastępowany nowym. Etykieta na stronie pokazuje czas ostatniej synchronizacji, a nie datę obowiązywania rozkładu. Odwiedzający niczego nie uruchamiają. Otwieranie przez `file://` nie jest obsługiwane, ponieważ przeglądarka blokuje pobieranie JSON — do lokalnego testowania potrzebny jest serwer WWW.
