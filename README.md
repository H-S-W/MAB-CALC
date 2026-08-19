# Sadeltak av lättbalk — momentstyv nock

Dimensioneringsunderlag för sadeltak av lättbalk (Masonite Beams) med
momentstyvt eller ledat nockförband. Förbandsmetoderna följer *The I-joist
Handbook* (2022) avsnitt 5.3.4.1 respektive 5.3.7. Materialvärdena kommer
ur tillverkarens **ETA 12/0018** och ur **EN 12369-1**,
förbindarkapaciteten räknas fram ur **EN 1995-1-1 8.2.2**.

> **ETA-utgåva:** allt vilar på ETA 12/0018 av 2023-10-26 — valt
> 2026-08-18 som den enda publicerade utgåvan. Utfärdaren har inte
> bekräftat statusen, så valet redovisas som antagande i varje körning.
> Se `docs/ERRATA.md` punkt 5b.

> **Status:** underlag, inte konstruktionshandling. Materialvärdena är
> riktiga och spårbara och hela kedjan är på plats — brottgräns, förband,
> upplag och nedböjning — men **lasterna i `input/projekt.toml` är
> fortfarande platshållare**, inklusive vindens c_pe-värden. Läs
> `docs/ERRATA.md` innan du använder tryckta kapaciteter ur handboken
> eller ETA:n.

## Kom igång

```bash
pip install -r requirements.txt    # beroenden (streamlit, matplotlib, plotly ...)
python -m streamlit run app.py     # webbgränssnitt i browsern
python run.py                      # samma beräkning på kommandoraden
python run.py --foresla            # sök balk och spikning (tomt fält = föreslå)
python run.py --jamfor             # momentstyv mot ledad nock
python -m pytest tests -q          # 789 tester
```

Appen körs lokalt. Streamlits statistikutskick är avstängt i
`.streamlit/config.toml`, så ingenting du matar in lämnar datorn.

## Publicera på Streamlit Community Cloud

Appen kan även köras hostat — men läs detta först:

- **Allt som matas in behandlas då på Streamlits servrar** (USA), inklusive
  koordinater. Lokal körning enligt ovan är fortsatt det privata valet.
- Repot ska vara **privat** på GitHub. `.gitignore` håller PDF:erna
  (upphovsrätt) och `input/.senaste_session.json` (personlig indata)
  utanför repot.
- Autosparet till fil är **avstängt i hostat läge** (delad server = delad
  fil); sessionen lever bara i webbläsarfliken där.

Steg: skapa ett privat repo på GitHub → pusha detta projekt → på
share.streamlit.io: New app → välj repot, branch `main`, main file
`app.py` → Advanced settings: **Python 3.12** → Deploy. Beroendena läses
ur `requirements.txt`.

## Vad som kontrolleras

| Kontroll | Metod |
|---|---|
| Balken: böjning, tvärkraft, axialkraft | ETA tab. 11/12 med tab. 17:s k_mod |
| Balken: interaktion M+N, knäckning i planet | EN 1995-1-1 6.2.3 / 6.3.2 |
| Sidostöd av tryckflänsen | ETA annex 3 tab. 19 — varnar, räknar vidare |
| Momentstyvt nockförband | handboken 5.3.4.1 + EC5 8.2.2; halvgruppsmetoden valbar (ERRATA punkt 7) |
| Ledat nockförband inkl. excentricitetsmoment | handboken 5.3.7 |
| Upplagstryck vid takfot | ETA ekv. 3–5 + tab. 6–9, verifierat mot tab. 13/14 |
| Nedböjning u_inst, u_freq, u_fin | EC5 2.2.3 + Limträhandbok del 2 ekv. 6.8; k_def delad i böj/skjuv (ETA tab. 18) |

Snittkrafterna kommer ur en 2D-ramanalys med **skjuvdeformation**
(Timoshenko, `GA` ur ETA:n — skjuvdelen är ~10 % av nedböjningen redan
statiskt och kryper 2,5–4× mer än böjdelen) och **nockens ändliga
rotationsstyvhet**. Nocken är en **skarv** — skivan är spikad i vänster
sparre av förbindarna på ena sidan fogen och i höger sparre av de på den
andra — så de två halvförbanden sitter i serie:

    1/K_grupp = 1/(K·n_snitt·I_vänster) + 1/(K·n_snitt·I_höger)

där I är **halvgruppens tröghetsmoment om sin egen tyngdpunkt**. Lika
halvor ger K·n·I_egen/2. Skivan är en fri kropp: när sparrarna roterar mot
varandra rör sig båda halvgruppernas tyngdpunkter åt *samma* håll, så
skivan följer med utan att vrida sig och Steiners term hör inte hit — att
lägga till den svarar mot en skiva som hålls fast mot translation, och ger
1,5 gånger för styvt. En oberoende energiminimering över skivans tre
frihetsgrader låser formeln i `test_forband_skarv.py`. K_u = ⅔·K_ser i
brottgräns, EC5 tab. 7.1. Fjädern kan stängas av i projektfilen.

**k_mod bestäms per lastkombination** (EC5 3.1.3(2)): kombinationer med
vind får momentan-k_mod och kan därför vara *mindre* farliga än samma
kombination utan vind — varje kombination provas därför både med och utan
vindlasten. Med platshållarlasterna provas 108 fall.

## Struktur

```
├── app.py                     webbgränssnitt (ingen ingenjörslogik)
├── run.py                     samma beräkning på kommandoraden
├── input/
│   ├── projekt.toml           geometri, laster, materialval, antaganden
│   └── material/              biblioteken du själv styr
│       ├── balkar.toml        72 balkar ur ETA 12/0018 + upplagsmetoden
│       ├── skivor.toml        OSB/3 och P5 ur EN 12369-1, plus plywood
│       ├── forbindare.toml    förbindarnas egna egenskaper
│       └── nedbojningskrav.toml  handboken s. 229
├── src/
│   ├── material.py            uppslagning i biblioteken
│   ├── forbindare_ec5.py      F_v,Rk ur EC5 8.2.2/8.3.1, K_ser ur tab. 7.1
│   ├── balk.py                balkens bärförmåga, ETA + EC5 6.2.3/6.3.2
│   ├── upplag.py              upplagstryck, ETA ekv. 3–5
│   ├── laster.py              egentyngd, snö (EN 1991-1-3), vindfall
│   ├── kombinationer.py       6.10a/6.10b, lyftfall, varaktighet per kombo
│   ├── ram.py                 2D-ram: Timoshenko, rotationsfjäder, lokal
│   │                          last; sadeltak + takstol_b1 (stödben,
│   │                          hanbjälke, underram)
│   ├── forband.py             momentstyvt förband + ledad nock 5.3.7
│   ├── berakning.py           hela kedjan, samlad
│   └── dimensionera.py        tomt fält = föreslå
├── tests/                     789 tester
└── docs/
    ├── ERRATA.md              avvikelser i handboken OCH i ETA:n
    ├── ETA-12-0018-2023-10-26.pdf
    └── Limtrahandbok-del-2-2018.pdf   (u_freq: ekv. 6.8, tab. 6.1)
```

**Biblioteken är dina.** Programmet har inga hårdkodade materialalternativ —
ta bort en rad ur `input/material/` och den går inte längre att välja.

## Var värdena kommer från

| Storhet | Källa |
|---|---|
| `M_k`, `EI`, `V_k`, `GA`, `N_ck`, `N_tk` | ETA 12/0018 tab. 11/12 |
| `f_m,k`, `E_f` per flänskvalitet | ETA tab. 4/5 |
| `rho_k`, `rho_mean`, `E_0,05` per flänskvalitet | SS-EN 338:2016 tab. 1 |
| k_mod, k_def för balken | ETA tab. 17/18 |
| Upplagskapacitet | ETA ekv. 3–5, tab. 6–9 |
| Krav på sidostöd | ETA annex 3 tab. 19 |
| OSB/3 och spånskiva P5 | EN 12369-1 |
| Plywood | handbokens exempel 5.3.4.1 — behöver DoP |
| Förbindarkapacitet, K_ser | EN 1995-1-1 8.2.2, 8.3.1, tab. 7.1 |
| Tillåten nedböjning | handboken s. 229 (Limträhandboken del 2 s. 89) |
| Frekvent kombination (u_freq) | Limträhandbok del 2 (2018) ekv. 6.8 — PDF:en i `docs/` |
| Lastkombinationer, γ_d, ψ-faktorer | **BFS 2024:6** tab. 3:1, 3:5, 3:6 — i `input/regelverk/` |
| `γ_M` för balken | handboken s. 232 — ETA:n deklarerar ingen |
| `q_p`, `c_pe` | EKS resp. EN 1991-1-4 tab. 7.4a — **du läser av dem** |
| `EA`, knäcklängd, ρ_m för K_ser | **härledda**, redovisas som antaganden |

Vindens formfaktorer är avsiktligt indata: tab. 7.4a ger båda tecknen för
lutningar kring 15–45° och båda ska anges — programmet bygger sedan alla
fall inklusive speglade (vind från båda hållen) och inre tryck, samt
lyftfallet med gynnsam egentyngd.

De härledda storheterna går att ändra i `[dimensionering]` i projektfilen
och redovisas i varje körning. Se README-historiken eller docstringarna i
`src/balk.py` och `src/berakning.py` för härledningarna.

## Vad som är verifierat

- `ram.py` mot slutna lösningar: qL²/8, qL²/12+qL²/24, dragstång,
  treledsramens H = qL²/(8f); **Timoshenko** mot 5wL⁴/384EI + wL²/8GA;
  **rotationsfjädern** mot slope-deflection-lösningen
  M = (wL²/12)·S/(S+4EI/L) och mot båda gränsfallen.
- `forband.py` mot handbokens exempel 5.3.4.1 och 5.3.4.2, med
  avvikelserna i `docs/ERRATA.md` låsta åt rätt håll.
- **Balkdatat** mot ETA:ns egna formler: `V_k` ur ekv. 6/7 och `GA`:s
  linjäritet stämmer på 72 av 72; `M_k` går ihop med `EI`, tab. 4/5 och
  ekv. 1–2 inom 1,3 % (avrundning i trycket).
- **Upplagsmodulen** mot ETA tab. 13/14: 60+ tryckta värden träffas inom
  1 %, inklusive hörnen där k₆ (H450/500), k₇ (förstärkta HB) och
  interpolerade k_A/k_B styr. Nyckelupptäckt: tabellkolumnerna 95 och
  145 mm är interpolerade ur tab. 7/8:s stödpunkter, och k_A kapas vid 1,0
  medan k_B extrapoleras.
- **Skivdatat** korsverifieras mot ETA:n (k_mod/k_def för livmaterialet är
  EC5-radernas värden).
- **Förbindarkapaciteten** landar på handbokens antagna värden: 0,370
  mot 0,36 kN/snitt i fläns, 0,331 mot 0,30 i liv.
- **Ramverkstakstolen b1** mot jämvikt, spegelsymmetri (med hänsyn till
  att rullagret låter hela ramen driva i sidled), nockledens M = 0,
  hanbjälkens ledade ändar och tryck, underramen som dragband, och
  underramens nedböjning mellan fritt upplagd och fullt inspänd.
- **Ledade nockförbandet** reproducerar 5.3.7-exemplets kontroll
  (F = 0,592 kN) — vilket samtidigt avgjorde ERRATA punkt 3: `n` i
  handbokens formel är spikantalet *per grupp*.
- **Webbgränssnittet** smoktestas med `AppTest`, inklusive att appens
  siffror är identiska med `run.py`:s.

## Vad som återstår

- **Riktiga laster.** Allt i `[laster]` är platshållare, inklusive c_pe.
- **Takstolstyp b1 räknas inte hela vägen än.** Ramen finns och är
  verifierad (`ram.takstol_b1`: stödben, hanbjälke, underram som
  dragband), men beräkningskedjan bygger fortfarande sadeltakstolen.
  Det som återstår är vindsbjälklagets laster, knutpunkterna 5.3.5/5.3.6
  och nedböjningskrav för underramen — bjälklagsraderna i handbokens
  tabell s. 229 är medvetet utelämnade ur biblioteket (otydligt tryck).
- **Vippning** utöver ETA tab. 19:s sidostödsvillkor, hålskärningar,
  brandlastfall.
- **Skruv** som förbindare (EC5 8.7 kräver effektiv diameter och egna
  regler), förborrade avståndskrav.

## Noteringar

**Upplaget är flaskhalsen, inte balken — och det redovisas separat.**
Med platshållarlasterna är reaktionen ~15 kN per takstol medan 45 mm
oförstärkt upplag ger F_Rd ≈ 5,5 kN — och kapaciteten följer *serien*
(a-parametern), inte balkhöjden. En högre balk hjälper alltså inte;
längre upplag, förstärkning eller HB-serien gör det. Därför är upplaget
utlyft ur takstolsbedömningen (användarbeslut 2026-08-18): det ingår
varken i `haller`/`varsta_utnyttjande` eller i balkvalet i `--foresla`,
utan får egen rad i sammanfattningen, egna fält (`upplag_utnyttjande`,
`upplaget_haller`) och en varning som pekar på längre upplagslängd eller
förstärkning i stället för balkbyte.

**Balken är en egen produkt — utom där ETA:n själv säger annat.**
ETA:ns tabell 3 visar att momentkapacitet, tvärkraft och upplagstryck är
*provade på den sammansatta balken* (30 provkroppar var). Därför tas de
tabellerade värdena rakt av och räknas aldrig om ur flänsvirke och skiva.
Men axialkraftskapaciteten är den enda rad i tabell 3 som saknar
provning, och avsnitt 1.2.4 hänvisar då tillbaka: *"calculated according
to EC5 using strength and stiffness values in EN 338. For C30+ use the
values for C30"*. Knäckningens E_0,05 är alltså 8 000 MPa ur
SS-EN 338:2016 — inte 0,67 × ETA:ns förhöjda 13 000 = 8 710, som vore
att låna EN 338:s kvot men vägra dess nivå. Skillnaden är 8,9 % på
knäcklasten, åt osäkra hållet.

**EKS är upphävt — programmet räknar enligt BFS 2024:6.** Boverkets nya
föreskrift upphävde BFS 2011:10 (EKS), och övergångstiden gick ut
2026-06-30. Skillnaden är inte kosmetisk: tabell 3:1 har bara **två**
brottgränskombinationer i stället för EN 1990:s 6.10a/6.10b, och ψ-faktorerna
för snö är **snözonberoende i tre band** där den lägsta zonen har ψ₂ = 0,1
mot 0,2. Författningstexten är fri enligt 9 § upphovsrättslagen och ligger i
`input/regelverk/bfs2024-6.toml` med paragraf- och tabellnummer. Kartorna i
figur 4:2 och 4:3 är däremot upphovsrättsskyddade (9 § andra stycket) och
finns inte i repot.

**Varje variabel last prövas som ledande — även i bruksgränsen.**
EN 1990 6.14a kräver det, och med platshållarlasterna är det snön som
styr. Men på en blåsig ort med låg snözon (s_k = 1,0, 45° taklutning,
q_p = 1,2) är det vinden: kombinationen G + W + ψ₀·S ger 31,3 mm mot
snö-ledande fallets 17,5 mm, alltså 1,66 i stället för 0,93. Samma
princip som k_mod-regeln nedan — det räcker inte att pröva den last som
ser störst ut.

**k_mod-subtiliteten är verklig.** Dimensionerande fall för både balken
och förbandet är kombinationen *utan* vind: vindens bidrag (ψ₀·q_p·c_pe)
är litet, men dess momentan-varaktighet höjer kapaciteten 37 %. Utan
utan-vind-fallen hade programmet friskrivit takstolen på fel grunder.

**Nockförbandets metod är ett medvetet val, och båda talen redovisas.**
Fogen är en skarv: skär man loss ena sparren hänger den bara i spikarna på
sin egen sida, så hela M, N och V måste passera den halvan. Handbokens
5.3.4.1 räknar i stället över hela spikbilden om fogens mitt. Löser man
skarven elastiskt träffar halvgruppsformeln lösningen exakt, medan
handbokens underskattar spikkraften 2,0 ggr i flänsen och 2,5 ggr i livet.

Projektet räknar ändå enligt **handboken** (`nockmetod = "handbok"`),
eftersom dess tal kan vila på provning som inte redovisas i texten — ETA:ns
tabell 3 visar att tillverkaren provar sina konstruktioner. Men valet är
inte tyst: halvgruppstalet räknas alltid fram och kommer som varning i
varje körning, med kvoten mellan metoderna. Se `docs/ERRATA.md` punkt 7.

**En mjukare nock flyttar problemet, den löser det inte.** Med skarven
korrekt räknad (K_r = 355 kNm/rad mot 2153 för en stel infästning) sjunker
nockförbandets utnyttjande till 0,76 och det dimensionerande balksnittet
flyttar från nocken (5,61 m) ut i fältet (2,34 m). Men nedböjningen växer:
u_fin blir 1,44 och är nu det som styr takstolen. Det är därför
fjäderstyvheten måste vara rätt — den avgör inte bara ett tal utan
*vilken kontroll som är dimensionerande*.

**Underflänsen är tryckt i nocken, och den har inget sidostöd.** ETA
tab. 19 kräver sidostöd av tryckflänsen var 350:e mm (H-serien) för att
M_k ska gälla. Taklakten stödjer överflänsen; vid negativt moment är det
underflänsen som är tryckt. Programmet varnar och räknar vidare. En ledad
nock löser problemet — momentet blir noll — men fältutnyttjandet och
nedböjningen ökar, och horisontalkraften finns kvar: `--jamfor` ställer
varianterna mot varandra.

**Osymmetrisk snö styr nedböjningen, inte nockmomentet.** För
nockmomentet ger det symmetriska fallet störst värde, men värsta
nedböjningen kommer ur osymmetrisk snö *plus vind* — det fall som ger
störst last på en enskild sparre.

**Bredare fläns hjälper inte nockförbandet** (hävarmen är h − 47 i alla
serier), men HB-serien vinner ändå: högre M_k, N_ck och framför allt
högst upplagskapacitet. Spånskiveliv ger högre V_k men kryper mer
(k_def 2,25 mot 1,50) — och är enda valet för HB i drag tills
ETA-erratan om N_tk är rättad.

**Överhöjning lönar sig först över en tredjedel av nedböjningen.**
Handbokens tabell gäller *ej* överhöjda element och fotnoten säger
"tabellvärdet /1,5" — läst bokstavligen en **strängare** gräns, precis
som EN 1995-1-1 tab. 7.2 kräver mer av `w_net,fin` (ℓ/250–ℓ/350) än av
`w_fin` (ℓ/150–ℓ/300). Ett strängare krav hör ihop med en
nettonedböjning, så `overhojd = true` kräver att överhöjningen anges i
mm; den dras av enligt EC5 ekv. 7.2 och **kapas vid egentyngdens
slutliga nedböjning** (Limträhandboken 6.2.4). Villkoret för att det ska
löna sig är `u_c > u/3` — en för liten överhöjning gör kontrollen
hårdare. Hela resonemanget med siffror står i `docs/ERRATA.md` punkt 6.

**Zigzag-spikningen är en förutsättning, inte ett val.** Utan minst 1d
förskjutning ur fiberlinjen gäller radreduktionen k_ef i EC5 8.3.1.1(8) —
beräkningen antar k_ef = 1 och redovisar det. `kolumner_flans = 2` ger
dubbla flansspikar med kolumnerna en halv delning förskjutna, men kräver
2·a4t + a2 = 19d ≤ 47 mm (tab. 8.2, kraft mot belastad kant): det ryms
först när d ≤ 2,4 mm, så med 2,5-spiken varnar programmet. Flänsbredden
hjälper inte — spiken sitter i flänsens 47 mm höga sidoyta.

**Skivans böjning räknas två gånger.** Handbokens `f_m` är plattböjning
(EN 310); för böjning i skivans plan är `f_t,0` den försvarbara
parametern. Programmet redovisar båda och dimensionerar på den senare
när den finns.
