"""Inspecciona la API de la version instalada de RAGAS (utilidad de desarrollo, no forma parte del pipeline)."""
import inspect, warnings
warnings.filterwarnings("ignore")
import ragas
from ragas import evaluate
import ragas.metrics as m

print("ragas", ragas.__version__)
print([n for n in dir(m) if any(s in n for s in ("Faith", "Precision", "Recall"))])
print(inspect.signature(evaluate))
from ragas.metrics import Faithfulness, LLMContextPrecisionWithReference, LLMContextRecall
for c in (Faithfulness, LLMContextPrecisionWithReference, LLMContextRecall):
    inst = c()
    print(c.__name__, "| columnas:", getattr(inst, "_required_columns", None), "| llm:", hasattr(inst, "llm"))
import ragas.llms as L
print([n for n in dir(L) if not n.startswith("_")][:30])
