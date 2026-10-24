# Decisions

First of all, I want to thank you for this excellent take-home assignment! I believe that only tasks like this can truly show how an engineer solves hard problems. In the future I'd love to use this assignment for candidates as a great example of a take-home.

I really enjoyed working on it — researching, thinking about optimizations and improvements. I want to be upfront with you: I was experimenting with the solution. I deliberately decided to use and simultaneously explore how «System One decision model» works, specifically the new JEV model from TypeSafe AI.

Your assignment was built around correctly matching strings and text — structured or unstructured. Historically there have been many approaches to solving this kind of problem. The cheapest approach is the deterministic one, where we use mathematical formulas and assign deterministic probability scores. In plain terms, this is called fuzzy matching. Pros: fast, easy to scale, very cheap. Cons: complex to implement and maintain. The next approach is using Machine Learning models — a classic ML pipeline where we collect historical data, train models, test models, and constantly tune them on new data. The most important thing here is normalizing and filtering the data, because without quality data there's no quality prediction. The modern approach of the last 4 years is using LLMs and AI Agents, where we do the same data preparation as for ML but at the end we call an AI Agent that solves the text comparison problem for us. This approach has plenty of pros and cons, but overall AI agents are damn good at semantic text comparison. Unfortunately, there's one big pain point — LLM cost. When we scale a product, sooner or later we realize that the monthly LLM bill exceeds our expectations, and that's the pain of most AI startups.

I experimented with using a «System One decision model» for text analysis by asking simple classification questions. These models are built purely for classification — answering true/false or returning a probability — and crucially, they don't generate text like an LLM does. I used JEV as a smart if-else for comparing objects against each other, semantically comparing two objects — text, sentences, characteristics. Pros: relatively cheap, fast, and easy to scale. Cons: you need to work carefully on your input prompts, because if you're selecting from a large list it's better to group items during the normalization stage first, and only then call JEV. My advice: keep input tokens under 2000 to get higher model accuracy.

## Results

Honestly, the results blew me away — I didn't expect them to be this good. First and foremost, «System One decision model» is very fast, with an average request time of 0.7s, which is great considering the total cost was only £0.3180 for a full run of 200k items (actually even less, since normalization and filtering run on top). I'm convinced this approach deserves a place in production. Thank you for this great opportunity to test our hypotheses. I think that after testing on real-world data, `precision`, `recall` and `f1-score` will drop to 0.75–0.8, because we need to normalize and filter the data even better. But for the test data, the final metrics look pretty promising.

Results for the pipeline of 200k items:

**Pipeline time:** 95.4s
**LLM calls:** 4818
**LLM spend:** £0.3180

```
              precision    recall  f1-score   support

          no       0.98      1.00      0.99       283
         yes       0.91      0.59      0.71        17

    accuracy                           0.97       300
   macro avg       0.94      0.79      0.85       300
weighted avg       0.97      0.97      0.97       300
```

## Improvements

1. Build an AI orchestrator agent to double-check conflicting or neutral JEV responses.
2. Implement fuzzy matching to further increase speed and pre-filter data before calling JEV. I have an example project for this =)
3. Add DeepEval for deeper model testing.
4. Extend and improve the Golden Dataset examples.
5. Implement a cleaner folder and file hierarchy.

## Problems

1. Fix output data format and add output validation — some data is currently not rendered correctly.
2. Rate limit errors when running 200k items. Running 500 items per batch with up to 500 batches in parallel triggered the error; dropping to 300 parallel batches at 500 items each had no errors.

```
Rate limit exceeded for typesafe-ai/jev for provider digitalocean:
this team's limit of 3000 requests per minute (per region) was reached.
Retry after 18s.
```

I added the full Claude conversation history to the claude-history folder. Claude rated me as a mid-level engineer =))

> **A confident middle with senior traits in systems thinking.** Knows what observability is, understands trade-offs (LLM cost vs accuracy, parallelism vs race conditions). Comfortable working with an intentionally broken baseline — doesn't waste time fixing v1, builds v2 from scratch. Doesn't get stuck on ambiguity — reads the options, makes a call with reasoning.

I read a ton of articles about JEV. Leaving a few here — sorry they're in Russian =) I was deep in research mode and read everything I could =))

- [habr.com/ru/articles/1085450](https://habr.com/ru/articles/1085450/) ★ Great article
- [habr.com/ru/articles/1087480](https://habr.com/ru/articles/1087480/)
- [habr.com/ru/articles/1084030](https://habr.com/ru/articles/1084030/)
- [habr.com/ru/articles/1092000](https://habr.com/ru/articles/1092000/)
- [habr.com/ru/articles/1089164](https://habr.com/ru/articles/1089164/) ★ Great article
- [habr.com/ru/articles/1086180](https://habr.com/ru/articles/1086180/)
