# Mein Zuhause – Alexa für Home Assistant

Eigenständiger privater Alexa-Skill, aufgebaut nach dem Relay-Prinzip von
„meine Solaranlage“. Eigene Cloudflare-D1-Datenbank **mein-zuhause** mit
EU-Jurisdiktion; eigener Worker. Die Solarinstallation wird nicht verändert.

Version 0.1.0 benötigt Home Assistant ab 2026.3 (lokales Integrations-Icon).
Es ist ein erster funktionsfähiger Entwicklungsstand. Worker und
Sprachlogik sind automatisiert geprüft. Die Installation in einer echten
Home-Assistant-Instanz und der Test auf einem Echo stehen noch aus.

## Verwendung

- „Alexa, frage mein Zuhause, ob das Garagentor noch offen ist.“
- „Alexa, frage mein Zuhause nach dem Status von Außenlicht.“
- „Alexa, frage mein Zuhause, was noch offen ist.“
- „Alexa, sage mein Zuhause, schalte das Außenlicht ein.“
- „Alexa, sage mein Zuhause, schließe das Garagentor.“

Es gelten die vollständigen Anzeigenamen aus Home Assistant. Bei mehrfach
vergebenen Namen fragt der Skill nach einem eindeutigen Namen. Die deutschen
Slotwerte im Alexa-Modell sind Beispiele: Für zuverlässige Erkennung vor
allem bei direkten Einmalaufrufen die tatsächlichen Namen in der Alexa-Konsole
unter `HOME_ENTITY` ergänzen und das Modell erneut bauen. Die Auswahl der
Freigaben erfolgt unabhängig davon ausschließlich in Home Assistant.

## Installation in Home Assistant

1. `dist/mein-zuhause-ha.zip` entpacken und den darin enthaltenen Ordner
   `custom_components/mein_zuhause` nach `/config/custom_components/` kopieren.
2. Home Assistant neu starten.
3. Einstellungen → Geräte & Dienste → Integration hinzufügen →
   **Mein Zuhause – Alexa**.
4. Worker-Adresse und Sync-Schlüssel aus der privaten lokalen Datei
   `.private/home-assistant-setup.json` eintragen.
5. Unter **Entitäten für Abfragen** etwa das Garagentor (`cover` oder
   `binary_sensor` mit passender Geräteklasse) auswählen.
6. Unter **Zusätzlich zur Steuerung freigeben** nur die gewünschten steuerbaren
   Entitäten auswählen. Eine Entität muss für Steuerung in beiden Listen stehen.
   Die zweite Liste kann leer bleiben. Eine Torfreigabe erlaubt Öffnen und Schließen.
7. Später kann die Auswahl über die Integrationsoptionen geändert werden.

### HACS

In HACS unter den benutzerdefinierten Repositorys
`https://github.com/kulmi84/mein-zuhause` vom Typ **Integration** hinzufügen,
**Mein Zuhause – Alexa** herunterladen und Home Assistant neu starten.
Danach die Integration wie oben unter Geräte & Dienste hinzufügen.
Die Entitätsauswahl liegt im Einrichtungs- und Optionsdialog von Home Assistant;
HACS übernimmt Installation und Updates.

## Alexa einrichten

1. In der Alexa Developer Console einen neuen **Custom Skill**, Sprache
   **Deutsch (DE)**, **Alexa-hosted (Python)** anlegen.
2. Anzeigename **Mein Zuhause**, Aufrufname **mein zuhause**.
3. `alexa/interaction-model.de-DE.json` im JSON-Editor importieren, die eigenen
   Entitätsnamen als Werte von `HOME_ENTITY` ergänzen und das Modell bauen.
4. Unter Code `alexa/lambda_function.py` als `lambda_function.py` übernehmen.
5. Eine Datei `relay_config.json` im selben Alexa-Codeordner anlegen:
   Inhalt aus `.private/alexa-relay_config.json` übernehmen und darin die
   `skill_id` durch die tatsächliche ID aus der Alexa-Konsole ersetzen.
6. Speichern, deployen und den Testmodus aktivieren.
7. Skill-Icons: `assets/mein-zuhause-108.png` und `assets/mein-zuhause-512.png`.
8. Im Simulator „öffne mein zuhause“ und danach die Garagentor-Abfrage testen.

Der Skill ist für die eigene Installation und das eigene Amazon-Konto gedacht.
Die festen privaten Relay-Schlüssel sind kein Mehrbenutzer-Account-Linking.
Ein öffentlicher Skill für andere Haushalte benötigt eine getrennte Benutzer-
und Kontoverknüpfung.

## Architektur und Verhalten

Home Assistant → ausgehendes HTTPS → eigener Worker → eigene D1-Datenbank.
Alexa-hosted Python liest den letzten Snapshot oder stellt einen Steuerbefehl ein.
Home Assistant holt Befehle ausgehend ab; kein Port und kein HA-Zugriffstoken
müssen dafür ins Internet freigegeben werden.

- Nur ausgewählte Entitäten und die Felder ID, Anzeigename, Zustand,
  Geräteklasse, Einheit und erlaubte Aktionen werden übertragen.
- Zustandsänderungen werden innerhalb von etwa 5 Sekunden erkannt. Bei
  unveränderten Werten erfolgt mindestens alle 60 Sekunden ein Heartbeat.
- Nach 180 Sekunden ohne Snapshot gelten Werte als veraltet. Alexa spricht
  diese nicht als aktuellen Zustand aus und nimmt keine Steuerbefehle an.
- Getrennte Schlüssel: `SYNC_TOKEN` für HA, `READ_TOKEN` für Alexa-Abfragen,
  `CONTROL_TOKEN` für Alexa-Steuerung. Alle API-Routen verlangen den passenden Schlüssel.
- Steuerbar sind Licht, Schalter, Ventilatoren und Eingabe-Schalter
  (ein/aus) sowie Cover (öffnen/schließen). Schlösser werden nur abgefragt.
- Befehle laufen nach 15 Sekunden ab, werden atomar beansprucht und nicht
  automatisch erneut ausgeführt. Ein verlorenes Abrufpaket kann deshalb einen
  Befehl verwerfen. Das verhindert doppelte Aktionen nach Verbindungsfehlern.
- HA prüft unmittelbar vor jeder Aktion nochmals die örtliche Freigabe und
  Verfügbarkeit. Ein Entzug über die Optionen gilt dort nach dem Neuladen.
- Alexa bestätigt „Befehl übermittelt“. Das ist keine Bestätigung der physischen
  Endposition. Für das Ergebnis erneut den Zustand abfragen.
- D1 enthält den letzten Snapshot und Befehle bis ungefähr einen Tag nach Ablauf;
  beim nächsten Abruf werden ältere Befehle entfernt. D1-eigene Sicherungsfristen
  können darüber hinaus gelten.
- Der 5-Sekunden-Abruf ergibt ungefähr 17.280 Worker-Anfragen pro Tag pro HA.
  Es gelten die Cloudflare-Kontingente des eigenen Kontos.

## Cloudflare erneut bereitstellen

Für die Entwicklung wurde eine separate DB angelegt; die persönliche
`wrangler.jsonc` enthält ihre Bindung und wird nicht veröffentlicht.
Für eine eigene Installation `cloudflare/wrangler.example.jsonc` nach
`cloudflare/wrangler.jsonc` kopieren, eine eigene D1-Datenbank anlegen und
deren DB-ID eintragen.

```powershell
python scripts/create_private_config.py
cd cloudflare
npx wrangler d1 execute mein-zuhause --remote --file schema.sql
npx wrangler deploy
npx wrangler secret bulk ../.private/cloudflare-secrets.json
cd ..
python scripts/finish_private_config.py https://DEIN-WORKER.workers.dev
```

Private Schlüssel liegen ausschließlich unter `.private/` (Git-ignoriert) und
in den Cloudflare-Secrets. Nicht in ein öffentliches Repository oder ein
Installationsarchiv aufnehmen. `create_private_config.py` ersetzt bestehende
Schlüssel nicht.

## Prüfungen und Paketbau

```powershell
python -m unittest discover -s tests -v
node --test cloudflare/worker.test.mjs
python scripts/build.py
```

Die Worker-Tests verwenden eine echte lokale SQLite-Datenbank für das D1-SQL.
Ein Home-Assistant-Laufzeittest ist auf diesem Windows-Arbeitsplatz nicht enthalten.

## Name und Icon

„Mein Zuhause“ ist der Projekt- und Aufrufname. Das angefragte Logo wird aus
der offiziellen monochromen Home-Assistant-Vorlage exportiert, ohne dessen
Geometrie zu verändern. Quellen und Markenhinweis: `assets/ATTRIBUTION.txt`.
Das Projekt ist eine private Community-Erweiterung und kein offizielles
Home-Assistant-Produkt. Eine Nutzung von „Home Assistant“ als eigenständigem
Produktnamen für eine Veröffentlichung ist gesondert mit dem Markeninhaber
zu klären.

Quellen:
- [Offizielle Home-Assistant-Logos](https://github.com/home-assistant/assets/tree/master/logo)
- [Home Assistant: Alexa Custom Skill](https://www.home-assistant.io/integrations/alexa.intent/)
- [Amazon: Aufrufnamen](https://developer.amazon.com/en-US/docs/alexa/interaction-model-design/design-the-invocation-name-for-your-skill.html)
- [Cloudflare D1](https://developers.cloudflare.com/d1/get-started/)
