#!/bin/bash
cd ~/rag-fds
while ! grep -q K6_FIN run_k6.log 2>/dev/null; do sleep 30; done
for Q in Q01 Q02 Q03 Q04 Q05 Q06 Q07 Q08 Q09 Q10; do
  M=$(cat evaluador.txt)
  for K in 3 6; do
    .venv/bin/python src/evaluacion/evaluar_ragas.py --resultados evaluacion/resultados_k$K.json --salida evaluacion/ragas_k$K.json --modelo $M --solo $Q >> ragas_k$K.log 2>&1
  done
  echo "$Q hecho $(date -u +%H:%M)" >> ragas_progreso.log
done
echo RAGAS_FIN >> ragas_progreso.log
