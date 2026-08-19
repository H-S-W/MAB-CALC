# Errata — Masonite Beams underlag

Avvikelser som hittats vid kontrollräkning av tillverkarens egna dokument.
Varje punkt har ett motsvarande testfall i `tests/`.

Dokument som granskats:

- *The I-joist Handbook*, 1:a uppl. april 2022 — punkt 1–3 nedan
- *ETA 12/0018*, utg. 2023-10-26 (RISE) — punkt 4–5 nedan, se
  `docs/ETA-12-0018-2023-10-26.pdf`
- *Limträhandbok del 2* (2018) och *EN 1995-1-1:2004+A1:2008* — punkt 6
  nedan, se `docs/Limtrahandbok-del-2-2018.pdf` resp. avsnitt 7.2

---

## 1. `M_PL.reinf.k` i exempel 5.3.4.1 (s. 287)

Handboken skriver:

```
W = 2 * b_PL * h² / 6 = 5.4e5 mm³
M_PL.reinf.k = W * f_m.k.PL = 5.7 kNm
M_PL.reinf.d = M_PL.reinf.k * k_mod/γ_M = 8.1 kNm
```

5,4·10⁵ mm³ × 22,5 MPa = **12,2 kNm**, inte 5,7 kNm. Det dimensionerande
värdet 8,1 kNm är däremot korrekt (12,2 × 0,8/1,2 = 8,1), så felet är
isolerat till den tryckta mellanraden. Sannolikt är 5,7 kopierat från
livförstärkningens `M_PL.web.k` på föregående sida.

**Konsekvens:** ingen. Räkna vidare med 8,1 kNm.

Test: `test_handbok_5_3_4_1.py::test_errata_karakteristisk_kapacitet_ytterskiva`

---

## 2. `M_web` i exempel 5.3.4.1 (s. 290) — den viktiga

Handboken anger för samma spikgrupp:

| storhet | tryckt värde |
|---|---|
| `F_nail.web` | 0,30 kN/snitt |
| `I_p` | 1,3·10⁶ mm² |
| `r` | 184,6 mm |
| `M_web = F·I_p/r` | **3,96 kNm** |

Med de tre indata handboken själv anger blir resultatet

```
0,30 × 1,26·10⁶ / 184,6 = 2,05 kNm
```

3,96 kNm förutsätter 0,58–0,60 kN per förbindare, dvs. **två skjuvsnitt**.

Det vore i sig försvarbart — livförstärkningen sitter på båda sidor och en
2,5×50 spik når genom 18 mm plywood + ca 10 mm liv + 22 mm in i motstående
skiva. Handbokens avsnitt 5.3.7 räknar också uttryckligen med två snitt för
plywood direkt mot liv (`V_ed = 0,6 kN/spik`).

**Men:** handbokens `N_Rd` i *samma* exempel blir 38,7 kN, vilket bara går
ihop med **ett** skjuvsnitt (0,36×56 + 0,30×64 ≈ 39,4). Och exempel 5.3.4.2
reproducerar sitt eget `M = 6,0 kNm` bara med ett skjuvsnitt i båda
grupperna. Exemplet är alltså internt inkonsekvent.

**Konsekvens:** handbokens `M_Rd = 6,52 kNm` är för högt. Med konsekvent
enkelsnitt blir det

```
M_Rd = 2,56 + 2,05 = 4,6 kNm      (–29 %)
```

**Detta projekt defaultar till `n_planes = 1`.** Vill du utnyttja två
skjuvsnitt måste du visa att villkoren i EN 1995-1-1 8.3.1.1 för
inträngningsdjup är uppfyllda för din spik och din livtjocklek, och sätta
`n_planes_liv = 2` i `input/projekt.toml`. Använd då två snitt i *både*
`M_Rd` och `N_Rd`.

Test: `test_handbok_5_3_4_1.py::test_errata_livgruppens_momentkapacitet`

---

## 3. Enheter på `I_p` i 5.3.5, 5.3.6 och 5.3.7

Polära tröghetsmomentet skrivs `I_p = 2,33·10⁻⁷ m⁴` respektive
`1,35·10⁻⁷ m⁴`. Storheten `Σ(xᵢ² + yᵢ²)` för punktförbindare har enheten
**m²**, inte m⁴, och exponenten stämmer inte heller: bakräknat ur
respektive exempels egna kraftkontroller landar värdena på ca 2,3·10⁶ mm²
och 1,35·10⁵ mm². Mantissorna verkar rätt, enhet och exponent inte.

**Bekräftat för 5.3.7** (s. 301–302): med `I_p` = 1,35·10⁵ mm² och
`n` = 21 — *halva* det totala spikantalet 42, dvs. gruppen på ena sidan
fogen — reproduceras exemplets kontroll exakt:
`F = 0,424·10⁶·135/135 000 + 3500/21 = 424 + 167 N = 0,591 kN` mot tryckta
0,592. Med `n` = 42 går det inte ihop. `n` i formeln är alltså spikantalet
per grupp, inte totalt, vilket exemplet inte säger ut.

**Konsekvens:** går inte att använda de tryckta `I_p`-värdena rakt av.
Räkna om gruppen från geometrin, och räkna `n` per grupp. Det ledade
nockförbandet i `src/forband.py::ledad_nock` gör precis det.

---

## 4. `N_tk` för HB-serien i ETA 12/0018, tab. 11 — den viktiga

Kolumnen för karakteristisk dragkapacitet är för hela HB-serien med OSB-liv
**identisk med kolumnen för momentkapacitet**, rad för rad:

| balk | `M_k` [kNm] | `N_tk` [kN] tryckt |
|---|---|---|
| HB200 | 16,3 | 16,3 |
| HB250 | 21,5 | 21,5 |
| HB300 | 26,6 | 26,6 |
| HB500 | 45,4 | 45,4 |

Det kan inte vara riktigt. En dragkapacitet i kN kan inte sammanfalla
numeriskt med en momentkapacitet i kNm för nio balkhöjder i rad. För H-,
HM- och HI-serierna gäller genomgående `N_tk ≈ 0,79 · N_ck`, vilket för
HB200 med `N_ck` = 222,0 kN skulle ge ca 175 kN — inte 16,3.

Att det är en klippmiss bekräftas av tab. 12, där samma HB-serie med
spånskiveliv har `N_tk` = 173,3 till 184,5 kN. Det ligger på just den nivå
som `N_ck`-kolumnen förutsäger. Det är alltså tab. 11 som är fel, inte
tab. 12.

**Konsekvens:** dragkapaciteten för HB-balkar med OSB-liv är okänd i den här
utgåvan. Värdena är satta till `-1` i `input/material/balkar.toml` och
programmet ska vägra utnyttja HB med OSB-liv i drag tills värdet är bekräftat
av Masonite Beams eller RISE. `N_ck` är opåverkad. Spånskivevarianten
`HB...s` är opåverkad.

Test: `test_eta_balkar.py::test_hb_med_osb_liv_har_ingen_dragkapacitet`

---

## 5. Två olika ETA-nummer i handboken

Handboken s. 36 visar **ETA 08/0012** intill EU-symbolen, medan s. 42 och
s. 43 hänvisar till **ETA 12/0018** för hållfasthet, styvhet,
upplagskapacitet och hålregler.

Det är 12/0018 som är gällande ETA för produkten. Den utgåva som används här
är daterad 2023-10-26 och ersätter i sin tur en utgåva från 2023-05-11, dvs.
den är nyare än handboken från 2022.

**Konsekvens:** ingen, så länge man använder 12/0018. Noteras för spårbarhet,
och som påminnelse om att handbokens tryckta siffror kan vara äldre än
ETA:ns.

### 5b. Är 2023-10-26 fortfarande gällande utgåva? (kontroll 2026-08-18)

**Oklart — och det går inte att avgöra utan att fråga utfärdaren.**

Vad som är belagt: dokumentet självt säger *"This version replaces:
ETA 12/0018, issued on 11/05/2023"*, är utfärdat av RISE på grundval av
**EAD 130367-00-0304** (Composite wood-based beams and columns), och den
svenska och engelska filen är byte-identiska. Ingen nyare utgåva har
hittats hos tillverkaren, EOTA eller RISE.

Vad som INTE är belagt: att den fortfarande gäller. Skillnaden spelar
roll:

- **ETA:er enligt CPR 305/2011 har ingen giltighetstid.** De gäller tills
  de ersätts eller *dras tillbaka*. De 50 åren i avsnitt 2 är produktens
  antagna livslängd, inte dokumentets. Vår utgåva kan alltså inte ha
  "gått ut" — men det finns då heller inget datum i den som kan bevisa
  att den lever.
- **EOTA:s post ger HTTP 404** (`eota.eu/etassessments/6955`), och
  dokumentet saknas i både registret över giltiga och det över ersatta
  ETA:er. Att posten är borttagen är minst lika förenligt med ett
  återkallande som med en registerlucka.
- **Enda positiva indikationen är tillverkarens egen DoP** MBAB-DOP-260310
  (2026-03-10), som länkar rakt till 2023-10-26-filen. Men samma DoP
  anger *ETAG 011* som grund där ETA:n anger EAD 130367-00-0304 — texten
  underhålls uppenbart inte noggrant, så den duger inte som exakt källa
  på utgåva.
- **CPR 305/2011 håller på att avlösas av förordning (EU) 2024/3110**,
  med övergångsregler för befintliga ETA:er. Hur RISE hanterar 12/0018 i
  den övergången är inte utrett.

**Beslut 2026-08-18: projektet räknar på 2023-10-26.** Det är den enda
publicerade utgåvan och inga siffror pekar åt annat håll. Valet redovisas
som första raden i `Resultat.antaganden` i varje körning, så att det följer
med i allt underlag.

**Kvarstår att verifiera** innan underlaget används skarpt: fråga RISE
(`certifiering@ri.se`, ange dok. 1220846) om gällande utgåva, att ETA:n
inte är återkallad, och varför EOTA-posten saknas; fråga parallellt
Masonite Beams tekniksupport. Skriv inte "gällande utgåva" som
faktapåstående i en leverans som ska myndighetsgranskas förrän svaret
finns.

**Källor som INTE ska litas på:** ByggfaktaDOCU visar fortfarande 2018 års
utgåva, och brittiska spanntabeller räknar på "ETA-12/0018 dated
14/08/2018". Gamla utgåvor ligger kvar och ser aktuella ut i flera år.

---

## 6. "Tabellvärdet /1,5" för överhöjda konstruktioner (s. 229)

Handbokens nedböjningstabell har rubriken **"Constructions without
precamber"** och fotnoten:

> For constructions with precamber the tabular value /1.5 should be used.

Samma sak står i källan bakom, Limträhandboken del 2 tab. 6.1 s. 89
("Ej överhöjda konstruktionselement" … "För konstruktionselement med
överhöjning gäller tabellvärdet ⁄1,5").

Meningen går att läsa på två sätt, och de skiljer sig med faktorn 2,25:

| läsning | vad som delas | u_fin för `allmant_utan_tak` |
|---|---|---|
| A: värdet L/n delas | (L/300)/1,5 | **L/450** — strängare |
| B: nämnaren n delas | L/(300/1,5) | L/200 — mildare |

**Det här projektet räknar enligt A.** Tre oberoende trådar pekar dit
och ingen pekar på B:

1. **Texten.** "Tabellvärdet" är cellens innehåll, `L/300`. Delat med
   1,5 blir det `L/450`.
2. **Tabellrubriken.** Båda tabellerna gäller uttryckligen *ej*
   överhöjda element. Fotnoten beskriver alltså ett annat kontrollfall,
   inte en rabatt på samma kontroll.
3. **EN 1995-1-1 avsnitt 7.2**, som har exakt samma konstruktion.
   Ekvation 7.2 definierar nettonedböjningen

   ```
   w_net,fin = w_inst + w_creep − w_c = w_fin − w_c
   ```

   och tabell 7.2 ger för balk på två stöd:

   | | `w_inst` | `w_net,fin` | `w_fin` |
   |---|---|---|---|
   | Balk på två stöd | ℓ/300 – ℓ/500 | ℓ/250 – ℓ/350 | ℓ/150 – ℓ/300 |

   Kravet på NETTOnedböjningen är alltså strängare än på den totala,
   med en faktor mellan 1,17 och 1,67 — och 1,5 sitter mitt i spannet.

**En strängare gräns hör ihop med en netto-nedböjning.** Ramanalysen
räknar bruttonedböjningen, som inte vet något om överhöjningen; att
jämföra den mot ett netto-krav vore strängare än båda läsningarna.
Därför kräver `nedbojning.overhojd = true` att överhöjningens storlek
anges i `overhojd_mm`, och den dras av innan jämförelsen — precis
`w_fin − w_c` enligt ekv. 7.2. Utan mått höjs ett fel i stället för att
tyst räkna fel.

**Överhöjningen kapas vid egentyngdens slutliga nedböjning** (med
krypning). Överhöjningen finns för att kompensera just den —
Limträhandboken 6.2.4 s. 87: *"Om balken till exempel har överhöjning
för att kompensera för nedböjningen förorsakad av egentyngd, bör
nedböjningsgränsen tillämpas endast på den del som förorsakas av
nyttolasten."* Utan kap skulle avdraget bli ett sifferknep som kan få
vilken balk som helst att gå igenom, och en överhöjning större än så
ger dessutom en uppåtbuktning. Kapet redovisas som varning.

**Brytpunkten:** överhöjning lönar sig först när `u_c > u/3`, eftersom
villkoret `1,5·(u − u_c) < u` ska vara uppfyllt. Med projektfilens
platshållarlaster (u_fin = 22,5 mm, egentyngdens slutliga nedböjning
8,5 mm):

| överhöjning | u_inst | u_freq | u_fin |
|---|---|---|---|
| ingen | 1,138 | 0,785 | 1,205 |
| 4,8 mm (egentyngd momentant) | 1,227 | 0,696 | **1,423** — sämre |
| 8,5 mm (egentyngd slutligt) | 0,856 | 0,325 | **1,127** — bättre |
| 12 mm eller mer | 0,853 | 0,322 | 1,124 (kapat till 8,5) |

En för liten överhöjning gör alltså kontrollen *hårdare*, inte lättare.

**Konsekvens:** vill du i stället ha läsning B får du ändra
`overhojd_faktor` i `input/material/nedbojningskrav.toml` — men skriv
då in källan för det valet.

Test: `test_berakning.py::test_overhojd_skarper_kraven`,
`::test_overhojd_utan_matt_ar_ett_fel`,
`::test_overhojningen_kapas_vid_egentyngdens_nedbojning`,
`::test_overhojning_under_en_tredjedel_lonar_sig_inte`

---

## 7. Momentstyva nockförbandet räknas PER HALVGRUPP, inte som handboken

Handbokens exempel 5.3.4.1 räknar spikgruppens momentkapacitet över
**hela** spikbilden, med `I_p` och `r` mätta från fogens mitt
(`n_flange = 4·14 = 56`, `I_p = 1,5·10⁶ mm²`, `r = 205,9 mm`).

Men fogen är en **skarv**. Skär man loss den ena sparren hänger den bara
i spikarna på sin egen sida av fogen — hela M, N och V måste passera den
halvan. Handbokens formel svarar mot att skivan vore fast inspänd vid
fogen, och det finns ingenting som spänner in den där.

**Avgjort numeriskt, inte genom tolkning.** Skarven går att lösa
elastiskt: skivan som fri styv kropp, spikarna som fjädrar, sparrarna
roterande mot varandra. Största spikkraft per överfört kNm:

| | flänsgruppen | livgruppen |
|---|---|---|
| Elastisk lösning | 283,9 N | 366,1 N |
| Handbokens `M·r_hel/I_hel` | 140,6 N | 147,3 N |
| Per halvgrupp `M·r_egen/I_egen` | **283,9 N** | **366,1 N** |

Halvgruppsformeln **är** den elastiska lösningen — 1,00 gånger, för båda
grupperna. Handbokens metod underskattar spikkraften med faktor 2,0
respektive 2,5 för den här geometrin.

**Konsekvens:** för projektfilens platshållarlaster går nockförbandet
från 0,761 (handbokens väg) till 1,854 — en faktor 2,4. I praktiken
underkänns de flesta nockförband av den här storleken.

### Beslut 2026-08-18: projektet räknar enligt 5.3.4.1

Handbokens metod är vald **tills vidare**, av ett skäl som väger:
kapaciteterna i handboken kan vila på provning som inte redovisas i
texten. ETA:ns tabell 3 visar att momentkapacitet, tvärkraft och
upplagstryck alla är *"calculation assisted by testing"* med 30
provkroppar — tillverkaren provar sina konstruktioner, och det vore inte
konstigt om knutpunkterna också har underlag som inte är tryckt.

Valet är en **inställning**, inte inbyggt:

```toml
[forband]
nockmetod = "handbok"     # eller "halvgrupp"
```

Båda vägarna räknas alltid fram, oavsett val. Den ovalda redovisas som
**varning i varje körning** med sitt tal och kvoten mellan dem, så att
ett medvetet val aldrig blir ett glömt val:

> Nockförbandet räknas enligt handbokens 5.3.4.1 (hela spikbilden om
> fogen) och får 0,761. Räknat per HALVGRUPP — vilket är den elastiska
> lösningen för en skarv — blir det 1,854, alltså 2,4 gånger mer. Valet
> av handboksmetoden förutsätter att det finns provningsunderlag bakom
> den.

**Halvgruppsmetoden** flyttar snittkrafterna från fogen till
halvgruppens tyngdpunkt, vilket lägger till excentricitetsmomentet
`V·d` — exakt samma steg som handboken själv gör i 5.3.7 för den ledade
nocken.

Metoden är låst mot den elastiska referenslösningen i
`tests/test_forband_skarvkontroll.py`. Det låsta
`test_handbok_5_3_4_1.py` är orört och reproducerar fortfarande
handbokens tryckta tal.

**Kantavståndet skärptes till 15d (2026-08-19):** granskningen belade
att någon fognära spik i varje momentstyv körning belastas MOT den
kapade änden — spegelsymmetrin (x, ±y) garanterar det — och då kräver
tab. 8.2 a3t = (10+5·cos α)·d, inte a3c = 10d. Programmet använder 15d
(a3t:s övre gräns) för alla första rader. Samtidigt rättades att den
LEDADE nocken (5.3.7-vägen) hade lämnats platt när stötfogsplaceringen
infördes — 4 av 32 lägen satt i motstående sparre och excentriciteten
underskattades 43 % — samt att skivornas egna kontroller fick förbandets
sqrt-k_mod i stället för skivans eget (≈7 % för högt för OSB).

**Spikmönstret "kant" är förval sedan 2026-08-19** (användarbeslut): handbokens ramspikning (fig. 5.30 s. 289) i livet i stället för fullt rutnät. Förslagssökningen provar alltid båda mönstren per geometri och väljer på minsta totalantal; förvalet gäller manuella körningar. Referenstalen flyttade K_ser 502,8 → 468,7 kNm/rad (färre spik i livet).

**Sidoförskjutning i koordinaterna (2026-08-19, användarbeslut):** spik från motstående sidor får inte sitta mitt för varandra (flänsspiken överlappar 17 mm inne i flänsen, livspiken delar genomgående linje). Sida −Y förskjuts `sidoforskjutning` × c/c från fogen i själva koordinaterna, som ren addition på sida A:s lägen — beräkning (I_p, K_r), skivlängder, ritning och CSV räknar på de verkliga lägena. K_ser 468,7 → 482,5 (förskjutningen ökar I_p). Samtidigt skärptes skivändens kantavstånd i minimimåttet till 15d (a3t) — spegelargumentet gäller även skivänden: minst en ände är belastad i varje momentstyv körning, och lyftfallet drar mot änden. **Rutnätssnappning (samma dag):** de stötfogsklampade startavstånden rundas UPP till rastret c/c-avstandet/2 + n·c/c, så hela spikbilden ligger på ETT ritbart rutnät (tvärlinjer från fogen, kritlinjer från skivkanten). Konservativt — spik flyttar från fogen. K_ser 482,5 → 499,1. Rasterbasen ar konfigurerbar (`rutnat_bas`): projektfilen anvander 1,0 = tvärlinjer pa hela n·25 (anvandarbeslut samma dag; 0,5 = handbokens 12,5-bas, kvar som kodförval for reproduktionstesterna). K_ser 499,1 → 507,3. Sedan `rutnat_ankare = "flansvinkel"` (samma dag): en tvärlinje går exakt genom vinkeln mellan undre flänsarna, (h/2)·tan(α) från fogen — kännbar referenspunkt på den färdiga takstolen; K_ser 507,3 → 523,6.

**Spikplaceringen vid fogen (tillägg 2026-08-18):** handbokens exempel
placerar första spikraden 12,5 mm från fogen i PLATTA koordinater. Med
den verkliga lodräta stötfogen hamnar då 6 av 28 flänslägen och 8 av 64
livlägen bokstavligen på fel sida av fogen (H300, 27°), och även raderna
på rätt sida underskrider kantavståndet till den kapade änden (a3,
tab. 8.2 — avstånd till virkesände). Programmet lägger därför första
raden per kolonn så att avståndet till fogplanet är minst 10d (a3c,
antagande — a3t kan krävas där kraften pekar mot änden). Det gör
spikbilden trappad på undre halvan och flyttar referenstalen; ritningen
och beräkningen använder samma koordinater.

**Att fråga tillverkaren:** varför 5.3.4.1 räknar över hela spikbilden.
Det kan finnas provningsunderlag bakom, eller en avsedd förenkling. Ta
den frågan i samma mejl som frågan om ETA-utgåvan (punkt 5b).

---

## Metodanmärkning (inte ett fel)

Handboken summerar `M_flange + M_web` som om båda spikgrupperna nådde sin
kapacitet samtidigt. Det förutsätter plastisk omlagring. Grupperna har olika
`I_p/r` och når därför sin kapacitet vid olika rotation. Summationen är
rimlig för duktila spikförband men bör inte pressas — särskilt inte om du
byter till grova skruvar, som är sprödare.

`kontrollera()` i `src/forband.py` fördelar därför lasten mellan grupperna i
proportion till deras kapacitet och redovisar utnyttjandegraden per grupp,
så att antagandet blir synligt.
