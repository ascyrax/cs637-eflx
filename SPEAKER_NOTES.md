# Speaker notes: Evaluating eFlx

CS637 video presentation, 26 slides. Limit: 25 minutes (a few minutes over is acceptable).

The notes are a guide: make these points in your own words. People naturally speak 2–3× longer than a written script, so each section shows both numbers.

## Ghada Suleiman (slides 1–9)

| Script read word for word | Natural speech (2–3× the script) | **Maximum for your recording** |
|---|---|---|
| 2:41 min | about 5:22–8:03 min | **7:30 min** |

### Slide 1: Evaluating eFlx

Hello, we are Ghada, Rishikesh and Suraj. We evaluate the ICCPS 2025 paper eFlx: we rebuilt it from scratch, reproduced it on real New York taxi data, critiqued it and extended it.

### Slide 2: First the paper, then our work

I first summarise the paper. Then Suraj and Rishikesh present our own work: evaluation, implementation, reproduction and new ideas. Navy badges mark the paper’s content; orange marks ours.

### Slide 3: A taxi fleet as a power plant on wheels

An e-taxi uses over 50 kWh a day, so a Manhattan fleet charges at about 100 megawatts. In emergencies, grids pay big consumers to cut demand within minutes: demand response. Unlike a factory, a fleet can shift when and where it charges without passengers noticing.

### Slide 4: A DR program has three stages

A DR program has three stages, Figure 1. In provision, the fleet keeps serving and gets ready, without charging extra. In service, it cuts charging for two hours. In recovery, it recharges. Since the call can come any time, the fleet must always be ready.

### Slide 5: Reacting helps; preparing helps more

The paper’s motivating example, Figure 2. A fleet that only reacts cuts 127.86 megawatt-hours; one that prepared in advance cuts 139.37, 9% more, serving the same passengers. The paper asks how to prepare best.

### Slide 6: Be ready for a call that can come any time

The question: how should the fleet dispatch and charge now, so that whenever a call comes it can cut as much charging as possible without losing passengers? Flexibility is charging with no call minus charging when responding. Three rules: the call time is unknown, no extra charging beforehand, and no worse service.

### Slide 7: The model: counting taxis, not tracking them

The model counts taxis rather than tracking them: vacant, occupied, charging or waiting, per region and battery level, in 20-minute slots. Each slot decides where taxis go and how many charge. Everything is linear, so each plan is a linear program.

### Slide 8: Why it is hard: the yardstick moves

The hard part: flexibility is measured against a baseline that is itself the policy being optimised, an infinite loop. The paper fixes the baseline to normal service, giving the bi-level problem in Figure 5, but solved exactly it has 1.5 million variables. So it predicts normal service instead, merging both levels into one linear program.

### Slide 9: eFlx: a closed-loop fleet controller

eFlx sits between the grid and the fleet, Figure 4. Algorithm 1 solves the linear program, re-predicts normal service and repeats until the plan settles. Algorithm 2 runs this every 20 minutes, always assuming the call may come next slot. Suraj now evaluates it.

## Suraj Singh Raman (slides 10–17)

| Script read word for word | Natural speech (2–3× the script) | **Maximum for your recording** |
|---|---|---|
| 7:03 min | about the same: this section is written as a full spoken script | **your call; ~7–7:30 min including the demo clip** |

### Slide 10: What the paper claims

Thanks, Ghada. So before we judge the paper, let’s be clear about what it actually claims. They test on about 13,000 taxis in Manhattan, with the emergency window from 5:20 to 7:20 in the evening. Compared to normal operation, which they call TRC, eFlx charges about 20% less during that window and gives about 5.5% more flexibility. They also say it comes within half a percent of an Oracle, a version that knows exactly when the call will come. And all of this costs only about 2% extra driving and waiting. One thing worth noticing: the big 20% number is about charging during the window; the flexibility gain itself is much smaller. These four numbers are what we went and tested.

### Slide 11: Our critical reading: strengths and gaps

Now our honest reading of the paper. On the good side, it’s an important problem that hasn’t been studied much. The trick they use to get out of that infinite loop is really neat. It’s fast enough to run live, and the comparisons are fair, because every method plays by the same rules. But we also found some gaps, and for most of them we actually did something about it. The biggest one: flexibility is measured against each policy’s own baseline, so a policy can look more flexible just by charging more in normal times. Second, eFlx always assumes the call comes in the next twenty minutes, which is quite pessimistic; that’s where our idea P-eFlx comes from. Third, the paper says a fleet could give up a little service to be more flexible, but never measures it, so we did. And it only looks at cutting load, never at soaking up extra power. Then some smaller things: several parameters are missing, the energy use is unrealistically high, a battery would last under five hours, and there are a couple of notation mix-ups, like the Qv and Qo descriptions being swapped. To check the claims properly, we had to rebuild the whole thing.

### Slide 12: Rebuilding eFlx with no code released

The authors didn’t release any code, so we basically used the paper as our spec and built everything from scratch in Python. This table maps each part of the paper to a file. model.py has the rules of the city, equations one to four: how taxis move, pick up passengers and charge. policies.py has all the strategies: normal operation, the response policy, eFlx itself, and the baselines. sim.py runs the plan, act, repeat loop and calculates the flexibility score. For Manhattan, the normal way of writing these problems was far too slow, so fastplan.py builds the exact same problems as sparse matrices, and that’s about 20 times faster. Down here is equation one turned into code: it simply says every available taxi gets exactly one decision. And wherever the paper left a number out, like the battery size or the number of chargers, we picked a value and wrote it down in NOTES.md.

### Slide 13: How we know our code is right

Of course, the next question is: how do we know our code is actually right? We did three things. First, after every single step the simulator checks that no taxi appears or disappears: a hundred taxis in, a hundred taxis out. Second, the toy city is small enough that we could check things by hand. And third, which I quite like, we wrote the optimisation twice: once in a readable way that follows the paper’s equations line by line, and once in the fast version. On four different test cases, both give exactly the same optimal value. That’s the output you see here.

### Slide 14: Toy model: the core idea reproduces

Before going to real data, we tried a tiny city: two regions, two charging stations, a hundred taxis, and the same 5:20 to 7:20 window. And the core idea does work. eFlx raises flexibility from about 870 to about 1270 kilowatt-hours, and cuts charging during the window by around 38%, without losing a single passenger. Here it’s basically as good as the Oracle. One thing to notice in the plot: right at 7:20, every policy jumps straight back to full charging. That’s a rebound the paper doesn’t really talk about.

### Slide 15: Same optimum, different answers

Now here’s something we didn’t expect. Remember the two versions of our code? They always reach the same optimal value. But these problems have lots of tied solutions, all equally good on paper, and the two versions often pick different ones. When you run a whole afternoon, those small choices add up, and the results differ by up to 14%. For example, the Oracle charges 650 kilowatt-hours with one version and 561 with the other. So when the paper reports a gap of just 0.52% to the Oracle, that could honestly be inside solver noise. We also learned the hard way that the Oracle has to see the whole DR window, otherwise it can even lose to eFlx. Okay, let me quickly show you the code running.

### Slide 16: Demo: anyone can rerun it

So this is our GitHub repository, and the README explains how to set everything up and run it. First, the validation test. It takes about four seconds, and there you go, both versions of the code agree. Next, the toy experiment, about seven seconds. It prints the same table you saw a minute ago and then regenerates the figure. The Manhattan experiments use exactly the same code, but they take a few hours to run, so for those we just show the saved results.

### Slide 17: Real data: NYC taxi trips, March 2024

For the real experiment, we used New York City’s public taxi data for March 2024, about two million weekday trips in Manhattan. At the evening peak, that’s around 2,400 trips every twenty minutes, and most trips, 84%, finish within one slot. The paper splits Manhattan into 38 regions based on the power grid, but that map isn’t public, so we grouped the 62 taxi zones into 12 regions. We kept the paper’s values wherever it gives them, like the 15 battery levels and the 5:20 window, and chose the rest ourselves, like 4,000 charging ports. With that, I’ll hand over to Rishikesh for the results.

## Rishikesh Sawant (slides 18–24)

| Script read word for word | Natural speech (2–3× the script) | **Maximum for your recording** |
|---|---|---|
| 2:10 min | about 4:21–6:31 min | **7:30 min** |

### Slide 18: Figs. 6 and 7: paper vs ours (3,200 taxis)

The paper’s Figures 6 and 7 beside ours. At the paper’s own 13,000 taxis, every policy cuts DR charging to zero, so nothing can be compared; we use 3,200 taxis. There the ordering holds in direction, with eFlx charging least, then R2I, then normal operation, but the error bars are large.

### Slide 19: Claim by claim: direction holds, size doesn’t

Claim by claim: eFlx cuts DR charging by 4.8%, not 20%, and lands 4.6% from the Oracle, not half a percent. Flexibility, plus 4% against 5.5%, is the closest match. Without the charging limit it is even worse than R2I and TES, and nearly all the gain comes from one day.

### Slide 20: Fig. 11 and Table 1: lead time and forecast error

Figure 11: longer preparation helps on the toy city, but on Manhattan only partly, peaking at 80 minutes. Table 1: with a 10% forecast error, flexibility drops 6.8%, not 1.3%, about 5% of passengers are missed, and eFlx’s edge almost vanishes.

### Slide 21: New use cases: when does eFlx help?

A fleet-size sweep: from 13,000 taxis down to 4,000, any policy can cut DR charging to zero. Only at 3,200 does some charging remain. So the paper’s fleet sits in the easy corner of its own problem. We also varied the DR start time.

### Slide 22: Absorbing surplus solar and wind power

Grids with surplus solar and wind want fleets to charge more. Reversing the response, our fleet can absorb only 0.1 megawatt-hours extra, because normal operation already uses every free charger. Offering both directions needs a two-sided plan.

### Slide 23: P-eFlx: plan for when DR is likely

Our first idea, P-eFlx, plans with a probability of when DR is likely instead of assuming the next slot. It cuts DR charging by 32% versus eFlx on the toy city and 2.6% on Manhattan, closing three quarters of the gap to the Oracle without knowing the start time.

### Slide 24: How much flexibility does a little service buy?

Our second idea prices the service compromise. On Manhattan, missing about 4% of passengers gives two and a half times the flexibility, while eFlx’s provisioning is worth under 1% of service.

## All three (slides 25–26)

| Script read word for word | Natural speech (2–3× the script) | **Maximum for your recording** |
|---|---|---|
| 0:33 min | about 1:07–1:40 min | **1:30 min** |

### Slide 25: What the paper did, and what we did

**Ghada:** The paper turned a hard bi-level problem into one fast linear program, claiming 20% less charging. 

**Suraj:** We rebuilt and validated it; our limits are chosen parameters, 12 regions and a fluid simulator. 

**Rishikesh:** On real data the idea holds, but the gain shrinks to about 5%, and we added three new ideas.

### Slide 26: Contribution

**Ghada:** Thank you for watching. 

**Suraj:** All our code, data and results are in our GitHub repository. 

**Rishikesh:** We look forward to your questions.

---
Script total: 1744 words, about 12.5 minutes if read word for word.
