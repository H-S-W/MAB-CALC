# Instruktioner för Claude Code

## Om projektet
Dimensionering av sadeltak i lättbalk med momentstyv eller ledad nock.
Enheter: kN, m för laster och ramanalys; mm för förbandsgeometri och
upplag. Håll den uppdelningen — `forband.py`, `forbindare_ec5.py` och
`upplag.py` växlar internt.

## Regler
- Ändra aldrig ett testfall för att få det att passera. `test_handbok_*`
  låser handboken, `test_eta_balkar`/`test_eta_upplag` låser ETA 12/0018,
  `test_ram*` låser slutna lösningar.
- **Inga materialvärden i koden.** Allt ligger i `input/material/*.toml`
  med källhänvisning. `src/material.py` slår upp, den innehåller inga tal.
- **Inga hårdkodade alternativ i gränssnittet.** `app.py` fyller sina
  dropdowns ur biblioteken och innehåller ingen ingenjörslogik. `run.py`
  och `app.py` ska räkna identiskt — det finns ett test för det.
- Nya EC5/EC1-formler ska ha referens till avsnitt/ekvation i docstring;
  ETA-värden ska ange tabellnummer.
- Platshållare märks PLATSHALLARE; härledda storheter märks HÄRLETT och
  redovisas i `Resultat.antaganden`.
- Kör `python -m pytest tests -q` innan du föreslår att något är klart.
  Python heter `python` på den här maskinen, inte `python3`.

## Fällor som redan kostat tid
- **k_mod bestäms per lastkombination** (EC5 3.1.3(2)) — och varje
  kombination måste provas BÅDE med och utan vind: vindens
  momentan-k_mod höjer kapaciteten 37 %, så utan-vind-fallet styr ofta.
  Kedjan gör detta; kortslut det inte.
- **Två k_mod-serier för balken** (ETA tab. 17): böjning 0,80 men
  tvärkraft 0,70/0,65 beroende på livmaterial. Tvärkraftens gäller även
  upplag i vissa fall (fotnoten).
- **k_def är två faktorer** (tab. 18): böjning 0,60 mot skjuvning
  1,50/2,25. Nedböjningen räknas som två fält (kör ramen med och utan GA;
  differensen är skjuvdelen).
- **N_tk för HB med OSB-liv är fel i ETA tab. 11** — står som -1,
  `Balk.N_tk` höjer fel. I drag (lyftfallet!) faller de balkarna.
- **k_h är redan inbakad i ETA:ns M_k.** Lägg inte till den igen.
- **Förbanden räknas som SPIKADE, inte limmade.** Handbokens egna
  knutpunktsexempel 5.3.4–5.3.7 nämner inte lim en enda gång (0 träffar
  mot 111 på "nail"); limmet i handboken sitter i fabriken — limfogen
  fläns/liv, MUF-limmet, fingerskarvarna — och i teorin om samverkan.
  Monteringslim på knutpunkten är därför ett UTFÖRANDEKRAV, inte
  kapacitet. Det spelar roll: limmas fogen strukturellt blir den i
  princip styv, och då gäller varken fjädermodellen (K_r) eller
  spikkraftskontrollen. EC5 talar om delar hopfogade med lim **eller**
  mekaniska förbindare, och tabellerar dem separat (annex C) —
  kapaciteterna får inte adderas, eftersom limfogen är storleksordningar
  styvare och tar allt tills den brister sprött.
- **Nockens kapacitetsmetod är ett VAL** (`forband.nockmetod`, ERRATA
  punkt 7). Förval `"handbok"` = 5.3.4.1, hela spikbilden om fogen —
  valt 2026-08-18 eftersom handbokens tal kan vila på oredovisad
  provning. `"halvgrupp"` = den elastiska skarvlösningen, 2–2,5 ggr
  strängare. BÅDA räknas alltid; den ovalda redovisas som varning i
  varje körning. Ändra inte förvalet utan att fråga.
- **Nocken är en SKARV, inte ett infästningsbeslag.** Skivan fäster i
  BÅDA sparrarna, så halvförbanden sitter i serie och styvheten räknas på
  halvgruppens I_p om SIN EGEN tyngdpunkt: K = K·n·I_egen/2 för lika
  halvor. **Lägg INTE till Steiners term** — skivan är fri att
  translatera och gör det (båda halvornas tyngdpunkter rör sig åt samma
  håll), så n·d² hör inte hit. Den varianten ger 1,5× för styvt och
  underskattar både fältmoment och nedböjning. Härledningen har varit fel
  två gånger; `test_forband_skarv.py` låser den med en oberoende Sedan 2026-08-18 löses fjädern i nockens
  VERKLIGA geometri (`EC5.K_rot_skarv_vriden`, samma transform som
  ritningen — `forband.vrid_till_nock` är enda källan): taklutningen
  höjer styvheten, 393 mot 355 kNm/rad vid 27°, och α = 0 återger
  slutna formeln exakt.
  energiminimering.
- **ETA tab. 5 ger MEDELvärdet av E_f**; knäckning kräver 5-percentilen.
  ETA avsn. 1.2.4 säger var den hämtas: *"To be calculated according to
  EC5 using strength and stiffness values in EN 338. For C30+ use the
  values for C30"* — alltså E_0,05 = 8 000 MPa, inte 0,67 × 13 000.
  Kvoten härleds ur `[en338]` i balkar.toml; `E05_kvot = 0` i
  projektfilen betyder härled. Samma sak för K_ser: tab. 7.1 vill ha
  rho_MEAN (EN 338), inte rho_k.
- **γ_M står inte i ETA:n** — handboken s. 232 ger 1,3, ligger i
  `[dimensionering]`.
- **Upplagets k_A kapas vid 1,0, k_B extrapoleras.** Så är ETA:ns egna
  tab. 13/14 framräknade; `test_eta_upplag` bevisar det.
- **`n` i handbokens F = M·r/Ip + N/n är per spikgrupp**, inte totalt
  (ERRATA punkt 3, avgjord mot 5.3.7-exemplet).
- **Skivans f_m är plattböjning**, inte böjning i planet (`[metod]` i
  skivor.toml).
- **Kordaavvikelsen parametriseras på nodernas LÄGE, inte index.**
  `takstol_b1` delar sparren vid hanbjälken och får då olika långa
  element; en indexparametrisering ger upp till 14 % fel åt osäkra
  hållet.
- **Överhöjningsfaktorn gäller HELA tabellcellen**, även mm-taket:
  handbokens cell lyder "L/200 (maximum 30 mm)". Skalas bara L/n blir
  överhöjning en lättnad för djurstall/maskinhall.
- **Överhöjning SKÄRPER kravet** (handboken s. 229: tabellen gäller ej
  överhöjda element, fotnoten säger "tabellvärdet /1,5" — samma
  konstruktion som EC5 tab. 7.2, där `w_net,fin` är strängare än
  `w_fin`). Kravet gäller nettonedböjningen, så `overhojd = true` kräver
  `overhojd_mm`; den kapas vid egentyngdens slutliga nedböjning och
  lönar sig först när `u_c > u/3`. Avgjort med användaren 2026-08-18,
  hela resonemanget i `docs/ERRATA.md` punkt 6.
- **Varje variabel last måste prövas som LEDANDE** (EN 1990 6.14a), även
  i bruksgränsen: snö ledande med vind på ψ₀ *och* vind ledande med snö
  på ψ₀. På en blåsig ort med låg snözon styr vind-ledande fallet — det
  gav 0,93 mot 1,66 i utnyttjande innan det rättades.
- **Kontakt i fogen gäller bara TRYCK** (handboken s. 290, EC5 8.8.5).
  `ram.internal` har N > 0 = drag, så avdraget kräver teckenkontroll —
  `abs(N)` krediterar halva DRAGkraften till en fog som gapar, och det
  är just lyftfallet som blir fel.
- **Spikbilden tar hänsyn till den LODRÄTA stötfogen** (2026-08-18):
  varje kolonns första rad läggs så att kantavståndet mot kapad ände är
  minst **15d** (a3t:s övre gräns — någon fognära spik belastas alltid
  mot änden i en momentbelastad grupp) — `forband.rader_langs_balken`.
  Gäller BÅDA nocktyperna; den ledade glömdes först och rättades
  2026-08-19. Skivornas egna kontroller får skivans EGET k_mod, inte
  förbandets sqrt-mix (den gäller bara förbindarna). Platt placering (handbokens
  exempel) lägger bokstavligen spikar i motstående sparre: 6 av 28
  flänslägen och 8 av 64 livlägen hamnade på fel sida vid 27°. Det
  flyttade referenstalen (K_ser 393→470 m.m.); gamla tal var för den
  platta bilden.
- **Plywoodens draghållfasthet FINNS i handboken**: f_t,90 = 7,0 MPa
  (5.3.4.2 s. 291). Svagare riktningen → konservativ oavsett montering,
  så plywooden räknas i planet som osb3/p5. Då dimensionerar SKIVAN
  förbandet, inte förbindarna — plattböjnings-f_m (22,5) redovisas
  parallellt.
- **Spikmönstret "kant" är FÖRVAL** (fig. 5.30 s. 289, användarbeslut
  2026-08-19): handbokens ramspikning i livet — kantrader + fulla
  kolumner de yttersta `rader_andblock` raderna, tomt i mitten.
  `dimensionera.foresla` provar alltid BÅDA mönstren per geometri och
  väljer på minsta totalantal; förvalet gäller manuella körningar.
  Referenstal med kant: K_ser 468,7 (rutnätets 502,8 står i testets
  kommentar).
- **Sidoförskjutningen är verklig geometri** (2026-08-19): sida −Y
  ligger `sidoforskjutning` × c/c längre från fogen, som REN addition
  på sida A (klampningen i `rader_langs_balken` får inte nolla den).
  `Forbindargrupp.sidor = (A, B)` bär uppdelningen; `skala_grupper`
  måste kopiera attributet. Skivändens minimimått använder 15d (a3t),
  samma spegelargument som stötfogen. Referenstal: K_ser 482,5.
- **Axlarna i spikrutnätet:** `forband.rutnat` lägger första argumentet
  i x-led, och x är TVÄRS balken (flänsgruppen sitter på ±c_flans/2).
  Det är alltså KOLUMNERNA som begränsas av skivhöjden; raderna löper
  längs balken och skivans längd finns inte i modellen.
- **EKS är UPPHÄVT.** BFS 2024:6 upphävde BFS 2011:10; övergångstiden gick
  ut 2026-06-30. Lastkombinationerna är nu tab. 3:1 med bara TVÅ
  alternativ — LK1 (γd·1,2·G + γd·1,5·Q_huvud + γd·1,5·ψ₀·Q_övr) och LK2
  (γd·1,35·G, ingen variabel last) — inte EN 1990:s 6.10a/6.10b.
  Gynnsam permanent last är Gk **utan** γd. Allt ligger i
  `input/regelverk/bfs2024-6.toml`; författningstext är fri enligt 9 §
  upphovsrättslagen, men **kartorna i figur 4:2/4:3 är det inte** och får
  inte in i repot.
- **ψ-faktorer slås upp, hårdkodas inte.** Snöns ψ₁ är 0,6 först vid
  snözon 3 och uppåt; 0,4 för snözon 2–2,5 och **0,3 för snözon 1–1,5**.
  BFS 2024:6 tab. 3:6 har TRE band, inte två, och ψ₂ är 0,1 i det lägsta
  bandet — inte 0,2. `material.psi_sno(S_0)` äger uppslagningen.
  "Snözon n = S_0 = n kN/m²" är HÄRLETT (ordet snözon definieras aldrig)
  och redovisas som antagande.
- **Skriv inte .py-filer med PowerShells Set-Content** (teckenkodning).
  Använd Write/Edit.

## Arkitektur i korthet
`berakning.kor(cfg)` är enda ingången: bygger lastfall (108 st med
platshållarna), sveper brottgräns med per-fall-k_mod, kör SLS-fallen
med/utan GA för böj/skjuv-delning, och returnerar `Resultat` som
gränssnitten bara ställer upp. `dimensionera.foresla` provar kandidater
med hela kedjan och redovisar alla. Rotationsfjädern K_r byggs av
spikgruppernas K_ser och går in i ramen som fjäder i nockelementets ände
(K_u i ULS, K_ser i SLS). Nocken är en SKARV: halvförbanden i serie,
räknade på halvgruppens tröghetsmoment om SIN EGEN tyngdpunkt — se
`EC5.K_rot_skarv`. Upplaget är utlyft ur `haller`/
`varsta_utnyttjande` och ur balkvalet i `dimensionera.foresla`
(användarbeslut 2026-08-18): det redovisas separat
(`upplag_utnyttjande`, `upplaget_haller`) med varning, eftersom åtgärden
är upplagslängd/förstärkning — inte balkbyte. `foresla` verifierar
spikkandidaterna i stigande storleksordning med full körning tills en
håller (K_r-återkopplingen).

## Möjliga nästa steg
1. Riktiga laster i projektfilen (EKS snözon, q_p, c_pe ur tab. 7.4a).
2. Takstolstyp b1 hela vägen. `ram.takstol_b1` finns och är verifierad
   (stödben momentstyva enligt 5.3.5, hanbjälke ledad enligt 5.3.6,
   ledad nock enligt 5.3.7, underramen dragband). Kvar: vindsbjälklagets
   laster, knutpunktskontrollerna och nedböjningskrav för underramen —
   bjälklagsraderna s. 229 är medvetet utelämnade ur biblioteket.
   OBS: appen är sedan 2026-08-19 slimmad till momentstyv nock — ledad
   och b1 nås via beräkningskärnan/run.py, inte via gränssnittet.
3. Skruvgren i forbindare_ec5 (EC5 8.7, kräver d_ef ur deklaration).

Klart 2026-08-18: u_freq (Limträhandboken del 2 ekv. 6.8, PDF:en ligger i
docs/) och zigzag-spikning (`kolumner_flans`; en andra kolumn kräver
19d ≤ 47 mm enligt tab. 8.2, dvs d ≤ 2,4 mm — flänsBREDDEN spelar ingen
roll, spiken går in i flänsens 47 mm höga sidoyta).
