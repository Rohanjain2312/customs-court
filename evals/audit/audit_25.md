# Judge spot-check sheet (optional)

Run `cc-subset80-A`. 25 cases: all 12 where the two judges disagree, then a random fill (seed 13). Judge 1 is Claude Opus 5.5, judge 2 is Claude Haiku 4.5, both in the Claude Code session. The question for each case: did the agent reach CBP's heading for the same legal reason? Write pass or fail on the last line. Nothing depends on this sheet.

## 1. atlas_test_00008  (judges disagree)

**Product.** a hydrogen gas sensor printed circuit board assembly

**Gold code.** 9027.10.2000. **Agent code.** 9027.10.20.00 (deciding rule: GRI 1).

**Agent reasoning.** A PCBA that carries a hydrogen sensor and electronics to measure gas concentration is itself an electrical gas analysis apparatus of heading 9027, and Section XVI note 1(m) keeps it out of chapter 85. HQ 967082 classified gas detectors with sensors measuring ppm of gas and displaying levels in 9027.10.20, separating mere alarms into 8531. If the board lacks the sensing element it would instead be a part in 9027.90.88.

**CBP reference.** `ruling:N335170`, in `evals/blind/judge/cc-subset80-A/packets.jsonl`.

- Judge 1: fail. Heading 9027 matches, but CBP classified the uncalibrated PCBA as an incomplete gas analysis apparatus under GRI 2(a), whereas the assistant treated it as a complete apparatus under GRI 1.
- Judge 2: pass. Both correctly classified under 9027.10.20 as an electrical gas analysis apparatus based on the essential character being the gas-detection function.
- Your verdict: ____

## 2. atlas_test_00013  (judges disagree)

**Product.** printed motor vehicle fuse cards

**Gold code.** 3926.20.9050. **Agent code.** 4911.99.80.00 (deciding rule: GRI 1).

**Agent reasoning.** NY F83391 (in force) classified printed motor vehicle fuse cards carrying a fuse chart: the self-adhesive plastic card in 3919.90.50.60 and the non-adhesive card as other printed matter in 4911.99.80. The description does not say whether the cards are self-adhesive, which decides the heading. The best guess is the non-adhesive printed matter line 4911.99.80.00, since Section VII note 2 sends printed plastics other than 3918/3919 goods to chapter 49.

**CBP reference.** `atlas_reasoning`, in `evals/blind/judge/cc-subset80-A/packets.jsonl`.

- Judge 1: pass. The CBP reference's gold code (3926) conflicts with its own text, which classifies the non-adhesive card in 4911 and the self-adhesive card in 3919 via Section VII note 2, exactly the split and basis the assistant gave.
- Judge 2: fail. Assistant chose 4911 (printed matter) but CBP classified under 3926 (plastic articles).
- Your verdict: ____

## 3. atlas_test_00017

**Product.** a steel air conditioning vent

**Gold code.** 7326.90.8587. **Agent code.** 7326.90.86.88 (deciding rule: GRI 1).

**Agent reasoning.** A steel air conditioning vent is a separate article that fits a duct opening; CBP treats such vents, grilles and return air panels as not integral parts of an air conditioning unit, so heading 8415 does not apply. NY N350010 (in force) classified steel return air vents/access panels in 7326.90.86.88, following earlier vent and grille rulings. The vent falls in the residual steel line 7326.90.86.88.

**CBP reference.** `atlas_reasoning`, in `evals/blind/judge/cc-subset80-A/packets.jsonl`.

- Judge 1: pass. Both classify the steel vent in heading 7326 because it is not a part of the HVAC machine itself but a residual other article of steel.
- Judge 2: pass. Both correctly classified under 7326 as a separate steel article (not an integral part of an AC machine).
- Your verdict: ____

## 4. atlas_test_00037

**Product.** Vacuum Vessel Housing and Elliptical Collector used in Extreme Ultraviolet (EUV) Scanner for semiconductor lithography

**Gold code.** 8486.90.0000. **Agent code.** 8486.90.00.00 (deciding rule: GRI 1).

**Agent reasoning.** The first-named article, the vacuum vessel housing, is a dedicated component of an EUV scanner, which is a machine of heading 8486. Under Section XVI note 2(b) and the heading's own 'parts and accessories' text, such a part goes to 8486.90.00.00. CBP has placed dedicated components of ASML EUV systems in 8486.90.00.00 (NY N358520, in force). The elliptical collector mirror may be an optical element of chapter 90 and should be classified separately.

**CBP reference.** `atlas_reasoning`, in `evals/blind/judge/cc-subset80-A/packets.jsonl`.

- Judge 1: pass. Both classify in heading 8486 as dedicated parts of a semiconductor-manufacturing EUV scanner, though the assistant hedged that the collector mirror might go separately to chapter 90.
- Judge 2: pass. Both correctly classified under 8486 as parts of semiconductor machinery; vacuum vessel housing and elliptical collector are integral components.
- Your verdict: ____

## 5. atlas_test_00047

**Product.** NATCELL and CAR T CELL (Protein)

**Gold code.** 3504.00.5000. **Agent code.** 3504.00.50.80 (deciding rule: GRI 1).

**Agent reasoning.** The description names two products only as 'Protein', without saying what protein they are or how they are used. If they are protein substances used to support NK or CAR-T cell culture, heading 3504 (other protein substances n.e.s.) applies, as in NY N249832 (laminin protein for cell culture, 3504.00.50, in force), giving 3504.00.50.80. If they are cytokines or antibodies, heading 3002 immunological products would apply, and if they are engineered cells, 3002.51 cell therapy products (NY N325758).

**CBP reference.** `atlas_reasoning`, in `evals/blind/judge/cc-subset80-A/packets.jsonl`.

- Judge 1: pass. Both classify the products in heading 3504 under GRI 1 as other protein substances not elsewhere specified.
- Judge 2: pass. Both correctly classified under 3504 as protein supplements derived from biological sources.
- Your verdict: ____

## 6. atlas_test_00063  (judges disagree)

**Product.** a coffeemaker imported from Mexico

**Gold code.** 8521.90.0000. **Agent code.** 8516.71.00.20 (deciding rule: GRI 1).

**Agent reasoning.** An electric coffeemaker is an electrothermic domestic appliance named in subheading 8516.71 (coffee or tea makers). Assuming the common automatic drip design, the statistical suffix is 8516.71.00.20, consistent with in-force ruling H88216 on electric automatic drip coffeemakers. Country of origin (Mexico) does not change the classification.

**CBP reference.** `atlas_reasoning`, in `evals/blind/judge/cc-subset80-A/packets.jsonl`.

- Judge 1: pass. The CBP reference text (HQ 557331) classifies the coffeemaker in 8516.71.0020 as an electrothermic coffee maker, matching the assistant, although the stated gold code 8521.90 conflicts with that text.
- Judge 2: fail. CBP correctly applied 8521.90.0000 for coffeemaker (heading 8521) but assistant chose 8516.71.00.20 (heading 8516); both are electrothermic appliances but different final classifications.
- Your verdict: ____

## 7. atlas_test_00064  (judges disagree)

**Product.** a woman's 100% nylon lace, knit dress with a 100% polyester knit slip liner

**Gold code.** 6114.90.1030. **Agent code.** 6104.43.20.10 (deciding rule: GRI 1).

**Agent reasoning.** The garment is a woman's knitted dress, provided for in heading 6104. The outer shell of 100% nylon (synthetic) knit lace controls the fiber subheading 6104.43, and the attached polyester slip liner does not change the classification as both are synthetic. With no wool, it falls in 6104.43.20 and the women's suffix .10, consistent with N020188 (women's nylon/spandex knit dress in 6104.43.2010).

**CBP reference.** `atlas_reasoning`, in `evals/blind/judge/cc-subset80-A/packets.jsonl`.

- Judge 1: fail. CBP (gold 6114, text 6104 for the dress) classified the polyester slip separately in 6108, whereas the assistant expressly rejected separate slip classification as an integral lining, contradicting the ruling.
- Judge 2: pass. Both CBP text and assistant classified woman's nylon lace dress in heading 6104; outer nylon fiber and GRI 1 principle control the classification.
- Your verdict: ____

## 8. atlas_test_00068

**Product.** propylene glycol

**Gold code.** 2914.50.5000. **Agent code.** 2905.32.00.00 (deciding rule: GRI 1).

**Agent reasoning.** Propylene glycol is a separate chemically defined acyclic diol, which chapter 29 note 1 places in chapter 29. Subheading 2905.32 names it expressly (propane-1,2-diol), and the only statistical line is 2905.32.00.00. No precedent ruling on the pure compound was found in the search, but the eo nomine subheading settles the classification.

**CBP reference.** `atlas_reasoning`, in `evals/blind/judge/cc-subset80-A/packets.jsonl`.

- Judge 1: pass. The CBP reference text classifies propylene glycol eo nomine in 2905.32, matching the assistant, although the stated gold code 2914.50 conflicts with that text.
- Judge 2: pass. CBP final text states 'The classification under HTSUS 2905.32.0000' for propylene glycol; assistant also chose 2905.32.00.00 with eo nomine named subheading basis.
- Your verdict: ____

## 9. atlas_test_00076  (judges disagree)

**Product.** polyester/epoxy powder coatings

**Gold code.** 3907.30.0000. **Agent code.** 3907.99.50.50 (deciding rule: GRI 1).

**Agent reasoning.** Powder coatings are polymer powders in primary form rather than paints dispersed in a medium, so they fall in chapter 39. Under chapter 39 note 4 a polymer blend goes to the heading of the polymer predominating by weight; hybrid powders are usually polyester-rich, giving other saturated polyesters, 3907.99.50.50 (H88731 placed a saturated polyester resin for powder coatings in 3907.99; the code it cites, 3907.99.0050, is now line 3907.99.50.50). If epoxy predominates, N239953 supports 3907.30.00.00, so the answer abstains on the resin ratio.

**CBP reference.** `atlas_reasoning`, in `evals/blind/judge/cc-subset80-A/packets.jsonl`.

- Judge 1: pass. Both place the powder coatings in heading 3907 as plastics in primary form rather than prepared pigments or paints, with the subheading turning on the resin predominating by weight.
- Judge 2: fail. CBP gold code 3907.30.0000 specifies epoxy resins but assistant chose 3907.99.50.50 assuming polyester predominates; same heading 3907 but different decisive basis.
- Your verdict: ____

## 10. atlas_test_00079

**Product.** forged connecting rods used in 14.8L diesel engines for Class 8 heavy trucks

**Gold code.** 8409.99.9110. **Agent code.** 8409.99.91.10 (deciding rule: GRI 1).

**Agent reasoning.** Forged connecting rods for a 14.8L diesel engine are parts suitable solely or principally for compression-ignition engines of heading 8408, so Section XVI note 2(b) places them in 8409, and Section XVII note 2(e) excludes them from 8708. Because the engines go into Class 8 heavy trucks (8701.2x/8704), subheading 8409.99.91 applies, with the statistical line .10 for connecting rods. N249760 placed piston pins for diesel engines in the same 8409.99.91 subheading.

**CBP reference.** `atlas_reasoning`, in `evals/blind/judge/cc-subset80-A/packets.jsonl`.

- Judge 1: pass. Both classify the connecting rods in heading 8409 as parts solely or principally for diesel engines installed in heavy vehicles.
- Judge 2: pass. Both CBP and assistant classified connecting rods in 8409 for compression-ignition engines; Section XVI note 2(b) directs engine parts to heading 8409.
- Your verdict: ____

## 11. atlas_test_00080  (judges disagree)

**Product.** a youth combo snorkel pack that includes swim goggles, a snorkel set, a mesh sport bag, and a molded plastic beach capsule for valuables

**Gold code.** 9506.29.0040. **Agent code.** 9506.29.00.80 (deciding rule: GRI 3(b)).

**Agent reasoning.** The combo pack is a GRI 3(b) retail set of goods of different headings put up together for snorkeling. The snorkel set is the principal article and gives the set its essential character, so the whole pack goes to 9506.29 as other water-sport equipment, statistical line .80. In-force ruling L81175 classified a children's swim combo (mask, snorkel, fins in a case) in 9506.29.0080.

**CBP reference.** `ruling:G84446`, in `evals/blind/judge/cc-subset80-A/packets.jsonl`.

- Judge 1: fail. Heading 9506 matches for the snorkel set, but CBP classified each component separately, whereas the assistant treated the pack as a GRI 3(b) retail set with snorkel-set essential character.
- Judge 2: pass. Both CBP and assistant classified snorkel combo pack in heading 9506.29 as water sport equipment set; statistical suffix differences (0040 vs 00.80) do not matter per instructions.
- Your verdict: ____

## 12. atlas_test_00083  (judges disagree)

**Product.** industrial robots imported without their programmed controllers

**Gold code.** 8479.50.0000. **Agent code.** 8479.50.00.00 (deciding rule: GRI 2(a)).

**Agent reasoning.** Industrial robots imported without their programmed controllers are incomplete machines; under GRI 2(a) the manipulator arm supplies the essential character of the finished robot. With no dedication to welding or material handling shown, they fall under the residual eo nomine provision 8479.50.00.00 for industrial robots n.e.s.i. HQ 962659 treated industrial robots imported incomplete (without end-of-arm tooling) under GRI 2(a) and upheld classification of non-dedicated robots in 8479.50.00.

**CBP reference.** `ruling:N335129`, in `evals/blind/judge/cc-subset80-A/packets.jsonl`.

- Judge 1: fail. Heading 8479 matches, but CBP classified the robot eo nomine as imported (without manipulator arms), whereas the assistant relied on GRI 2(a) with a manipulator arm supplying essential character, contrary to the ruling's facts.
- Judge 2: pass. Both CBP and assistant classified industrial robots in 8479.50.0000; GRI 2(a) applies to incomplete machines where manipulator provides essential character.
- Your verdict: ____

## 13. atlas_test_00085  (judges disagree)

**Product.** orthodontic instruments

**Gold code.** 9022.13.0000. **Agent code.** 9018.49.80.40 (deciding rule: GRI 1).

**Agent reasoning.** Orthodontic instruments are instruments used in dental sciences, named by heading 9018 and excluded from the general tool headings of chapter 82. Assuming they are hand-held pliers, cutters and similar tools, they fall in 9018.49.80 and the statistical line for dental hand instruments, .40. I85144 confirms that orthodontic articles are classified in 9018.49.80 (it used the residual .80 line for non-hand-instrument mixing trays).

**CBP reference.** `atlas_reasoning`, in `evals/blind/judge/cc-subset80-A/packets.jsonl`.

- Judge 1: pass. The CBP reference text (HQ 559147) classifies the orthodontic instruments in 9018.49.80 as dental hand instruments, matching the assistant, although the stated gold code 9022.13 conflicts with that text.
- Judge 2: fail. CBP final statement says 'HTS US Code 9022.13.0000 accurately reflects' (heading 9022) but assistant chose 9018.49.80.40 (heading 9018); headings do not match.
- Your verdict: ____

## 14. atlas_test_00088

**Product.** an electrical deicer used on aircraft to prevent ice build-up

**Gold code.** 8516.80.4000. **Agent code.** 8516.80.40.00 (deciding rule: GRI 1).

**Agent reasoning.** An electrical aircraft deicer is an electric heating resistor that warms surfaces to prevent ice formation. Section XVII note 2(f) excludes chapter 85 electrical equipment from aircraft parts, and heading 8516 names electric heating resistors. The HTSUS has a specific line, 8516.80.40.00, for heating resistors assembled only with a simple insulated former and electrical connections used for anti-icing or deicing. No precedent ruling on an aircraft deicer was found in the searches.

**CBP reference.** `atlas_reasoning`, in `evals/blind/judge/cc-subset80-A/packets.jsonl`.

- Judge 1: pass. Both classify the deicer in heading 8516 as an electric heating resistor assembled with a simple insulated former and connections for anti-icing or deicing.
- Judge 2: pass. Both CBP and assistant classified aircraft electric deicer in 8516 as electric heating resistor; Section XVII note 2(f) keeps it in heading 8516 not aircraft parts.
- Your verdict: ____

## 15. atlas_test_00091

**Product.** various metalworking tools including metal slitting saws, taps, threading tools, drills, reamers, boring tools, and milling tools

**Gold code.** 8211.93.0000. **Agent code.** 8202.31.00.00 (deciding rule: GRI 1).

**Agent reasoning.** The description lists several different interchangeable metalworking tools that are not a retail set, so the first-named article, metal slitting saws, is classified. Heading 8202 expressly names slitting and slotting saw blades, and subheading 8202.31 covers circular saw blades with a working part of steel, giving 8202.31.00.00 on the assumption of HSS blades. The other tools fall in the heading 8207 subheadings for their kind. No precedent ruling specific to slitting saws was found in the searches.

**CBP reference.** `atlas_reasoning`, in `evals/blind/judge/cc-subset80-A/packets.jsonl`.

- Judge 1: pass. The CBP reference text classifies each tool separately with the metal slitting saws in 8202.31 as steel circular saw blades, matching the assistant's first-named-article analysis, although the stated gold code 8211.93 conflicts with that text.
- Judge 2: pass. CBP text classifies first-named metal slitting saws in 8202.31.0000 as circular saw blades; assistant chose 8202.31.00.00 with same heading and basis.
- Your verdict: ____

## 16. atlas_test_00109  (judges disagree)

**Product.** choker grapples and slack-pulling carriages used in the logging industry

**Gold code.** 8431.49.1090. **Agent code.** 8431.39.00.70 (deciding rule: GRI 1).

**Agent reasoning.** Choker grapples and slack-pulling carriages are dedicated working components of cable yarding and log handling equipment, which is lifting and handling machinery of heading 8428. Under Section XVI note 2(b) they fall in heading 8431 as parts of 8428 machinery, and the statistical line 8431.39.00.70 specifically covers parts of woodland log handling equipment of 8428.90.0310. H81340 classified a grapple hanger for log loaders as parts of 8428 machinery in 8431.39.

**CBP reference.** `atlas_reasoning`, in `evals/blind/judge/cc-subset80-A/packets.jsonl`.

- Judge 1: pass. Both classify the grapples and carriages in heading 8431 as parts suitable solely or principally for logging machinery of headings 8425-8430, differing only at the subheading level (8428 vs 8426 host machine).
- Judge 2: fail. CBP classifies choker grapples in 8431.49.1090 as parts of logging machinery of 8431.49 but assistant chose 8431.39.00.70 as parts of handling machinery of 8428; subheadings 8431.49 vs 8431.39 differ.
- Your verdict: ____

## 17. atlas_test_00114

**Product.** traffic signal parts from China, specifically an external housing/shell made from Lexan plastic and a cast aluminum bracket for attaching a traffic light

**Gold code.** 8530.90.0000. **Agent code.** 8530.90.00.00 (deciding rule: GRI 1).

**Agent reasoning.** The Lexan external housing is identifiable as a part of a traffic signal, which is road traffic control equipment of heading 8530. Under Section XVI note 2(b), a part suitable solely or principally for that apparatus is classified with it, in 8530.90.00.00. NY N359472 (in force) classified a housing for a roadway pedestrian warning light in 8530.90.0000. The first-named article (the housing) decides; the bracket should be classified separately, most likely in the same line.

**CBP reference.** `atlas_reasoning`, in `evals/blind/judge/cc-subset80-A/packets.jsonl`.

- Judge 1: pass. Both classify the traffic signal housing in heading 8530 as a part dedicated to road traffic control equipment.
- Judge 2: pass. Heading 8530 matches; both rely on Section XVI note 2(b) for parts of traffic signals.
- Your verdict: ____

## 18. atlas_test_00130

**Product.** laminated BOPP/PET film

**Gold code.** 3920.20.0000. **Agent code.** 3920.20.00.55 (deciding rule: GRI 6).

**Agent reasoning.** A laminate of BOPP and PET films is a noncellular, unreinforced plastic film of heading 3920. The 6-digit subheading depends on which polymer predominates by weight: polypropylene gives 3920.20 and PET gives 3920.62. The weight split is not stated. Assuming BOPP predominates, the code is 3920.20.00.55, consistent with NY K84976 (in force), which classified multilayer BOPP sheets in 3920.20.0000.

**CBP reference.** `ruling:K85180`, in `evals/blind/judge/cc-subset80-A/packets.jsonl`.

- Judge 1: pass. Both classify the laminated film in heading 3920 as noncellular plastic film laminated with other plastics, of polymers of propylene.
- Judge 2: pass. Heading 3920 matches; both apply GRI 6 for laminated plastic film with BOPP predominating.
- Your verdict: ____

## 19. atlas_test_00133

**Product.** 2,2'-Dithiosalicylic Acid

**Gold code.** 2930.90.2900. **Agent code.** 2930.90.29.00 (deciding rule: GRI 1).

**Agent reasoning.** 2,2'-Dithiosalicylic acid is an aromatic disulfide carrying carboxylic acid groups. Under chapter 29 note 3, a compound that fits both the carboxylic acid heading and the organo-sulfur heading goes to the one last in numerical order, 2930. As an aromatic compound not specially named, it falls in 2930.90.29.00. NY N264976 (in force) classified the analogous aromatic disulfide acid 3,3'-dithiobishydrocinnamic acid in 2930.90.2900.

**CBP reference.** `atlas_reasoning`, in `evals/blind/judge/cc-subset80-A/packets.jsonl`.

- Judge 1: pass. Both classify 2,2'-dithiosalicylic acid in heading 2930 as an organo-sulfur compound.
- Judge 2: pass. Heading 2930 matches; both apply Chapter 29 note 3 for compound fitting organo-sulfur & carboxylic acid.
- Your verdict: ____

## 20. atlas_test_00138

**Product.** a Girls Princess Costume Set consisting of a long dress, crown, belt, and necklace made from synthetic fibers and a Hippie Costume consisting of pants, blouse, vest, flower, headband, sunglasses, and necklace with various materials

**Gold code.** 6104.43.2020. **Agent code.** 6104.43.20.20 (deciding rule: GRI 3(b)).

**Agent reasoning.** The Princess Costume Set is the first-named article. It is a GRI 3(b) set in which the long synthetic dress gives the essential character over the crown, belt and necklace. A well-made child's costume dress is wearing apparel, not a chapter 95 festive article, so it goes in heading 6104 when knit. NY H80172 (in force) classified a child's Princess Costume dress in 6104.43.2020 (girls' knit synthetic dress). The knit/woven construction and the separate Hippie Costume are open points.

**CBP reference.** `ruling:H88105`, in `evals/blind/judge/cc-subset80-A/packets.jsonl`.

- Judge 1: pass. Both classify the Princess Costume set in heading 6104 because the knit synthetic dress gives the set its essential character under GRI 3(b), with the Hippie Costume items classified separately.
- Judge 2: pass. Heading 6104 matches; both apply GRI 3(b) and Chapter 95 note 1 for well-made girl's costume dress.
- Your verdict: ____

## 21. atlas_test_00165  (judges disagree)

**Product.** a crankshaft sensing blade used in spark ignition internal combustion piston engines

**Gold code.** 8409.91.5085. **Agent code.** 8409.91.99.90 (deciding rule: GRI 1).

**Agent reasoning.** A crankshaft sensing blade is dedicated to spark-ignition piston engines of heading 8407 and is not a good named in its own chapter 84/85 heading, so Section XVI note 2(b) sends it to 8409.91. Without a stated vehicle or marine application it falls in the residual 8409.91.99.90, as with the small-engine pushrod in NY F88714 (in force). NY N270502 (in force) instead classified a similar iron sensor wheel as an article of iron in 7326.90.8588, which is a real alternative risk; if the blade is for a passenger vehicle engine the line would be 8409.91.50.85.

**CBP reference.** `ruling:N290182`, in `evals/blind/judge/cc-subset80-A/packets.jsonl`.

- Judge 1: pass. Both classify the dedicated engine component in heading 8409 as a part suitable solely or principally for spark-ignition engines of heading 8407.
- Judge 2: fail. CBP classified as 8409.91.50.85 (parts for spark ignition engines in specific vehicles) vs assistant chose 8409.91.99.90 (residual without stated vehicle); different subheading due to different factual assumptions.
- Your verdict: ____

## 22. atlas_test_00170  (judges disagree)

**Product.** parts of beer dispensing equipment, including a valve head, coupling head, stout faucet, and spare parts for stout faucets

**Gold code.** 8481.90.5000. **Agent code.** 8481.80.10.50 (deciding rule: GRI 1).

**Agent reasoning.** The description lists several articles; the first-named valve head is a complete hand-operated valve and so is a good of heading 8481, which Section XVI note 2(a) keeps in its own heading rather than as a part of beer dispensing machinery. NY H89948 (in force) shows CBP treating beer-tap hardware under heading 8481, split by copper or iron/steel material. Assuming brass and a working pressure under 850 kPa, the line is 8481.80.10.50; if stainless steel, 8481.80.30.90.

**CBP reference.** `atlas_reasoning`, in `evals/blind/judge/cc-subset80-A/packets.jsonl`.

- Judge 1: pass. Both classify the beer-dispensing items in heading 8481 as taps/valves (and parts) rather than as parts of beer-dispensing machinery of 8418, differing only at subheading level.
- Judge 2: fail. CBP classified as 8481.90 (parts of taps/valves) vs assistant as 8481.80 (complete valve/tap); different subheading and different legal basis.
- Your verdict: ____

## 23. atlas_test_00171

**Product.** a bib style apron made of 100% cotton fabric

**Gold code.** 6211.42.0081. **Agent code.** 6211.42.10.92 (deciding rule: GRI 1).

**Agent reasoning.** A bib apron is a garment of heading 6211, and being unisex it is treated as women's under chapter 62 note 9. NY G83072 (in force) classified a woven cotton bib apron as a women's other garment of cotton (then 6211.42.0081, category 359). In the current tree that falls in 6211.42.10 and the residual statistical line 6211.42.10.92, since the apron is not hospital or laboratory apparel.

**CBP reference.** `ruling:L80759`, in `evals/blind/judge/cc-subset80-A/packets.jsonl`.

- Judge 1: pass. Both classify the woven cotton bib apron in heading 6211 as a women's or girls' other garment of cotton.
- Judge 2: pass. Both classified as 6211.42 (women's cotton garments); heading and subheading match; differences in statistical suffix only due to tariff tree restructuring.
- Your verdict: ____

## 24. atlas_test_00186  (judges disagree)

**Product.** a battery-operated sound reproducing apparatus designed for hunting that can reproduce various predator calls

**Gold code.** 8519.81.3020. **Agent code.** 8519.81.30.20 (deciding rule: GRI 1).

**Agent reasoning.** A battery-operated device that plays back stored predator calls is a sound reproducing apparatus of heading 8519; the electrical playback function is more specifically described there than as a decoy call of 9208 or a hunting requisite of 9507. With sounds on semiconductor media and no recording capability, it falls in 'sound reproducing only: other', 8519.81.30.20. NY N334310 (in force) shows CBP placing a small battery-operated sound device in 8519.81, at .41.50 because that device also recorded.

**CBP reference.** `atlas_reasoning`, in `evals/blind/judge/cc-subset80-A/packets.jsonl`.

- Judge 1: fail. Heading 8519 matches, but CBP treated the device as a set (with remote) whose sound reproducing component gives essential character (GRI 3(b)), whereas the assistant classified under GRI 1 without addressing the set.
- Judge 2: pass. Both classified as 8519.81.30.20 (sound reproducing apparatus); same code with notation difference.
- Your verdict: ____

## 25. atlas_test_00188

**Product.** sucker rods and sucker rod couplings

**Gold code.** 8413.91.90. **Agent code.** 8413.91.90.31 (deciding rule: GRI 1).

**Agent reasoning.** Sucker rods link the surface pumping unit to the down-hole reciprocating pump and are used solely with those pumps, so under Section XVI note 2(b) they are parts of pumps of 8413.50 classified in 8413.91.90. HQ H310618 (in force) addressed sucker rods and couplings that had been liquidated under 8431.43.80 and considered the protestant's claim under 8413.91.90, noting CBP's earlier NY R00333 placing similar rods there; the full holding was truncated in the tool output, so the ruling is relied on for the analysis framework. The current tree has a dedicated line for sucker rods, 8413.91.90.31.

**CBP reference.** `atlas_reasoning`, in `evals/blind/judge/cc-subset80-A/packets.jsonl`.

- Judge 1: pass. Both classify the sucker rods in heading 8413 as parts of pumps for liquids (8413.91.90), consistent with the ENs and NY R00333.
- Judge 2: pass. Both classified as 8413.91.90 (parts of pumps); heading and subheading match; Section XVI note 2(b) used by both; assistant adds statistical suffix .31.
- Your verdict: ____
