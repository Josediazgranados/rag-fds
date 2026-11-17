#!/bin/bash
cd ~/rag-fds
.venv/bin/python src/rag/correr_preguntas.py --preguntas evaluacion/preguntas.json -k 3 --salida evaluacion/resultados_k3.json > run_k3.log 2>&1
echo K3_FIN >> run_k3.log
.venv/bin/python src/evaluacion/evaluar_ragas.py --resultados evaluacion/resultados_k3.json --salida evaluacion/ragas_prueba2.json --solo Q01 Q02 > ragas_prueba2.log 2>&1
echo PRUEBA2_FIN >> ragas_prueba2.log
.venv/bin/python src/rag/correr_preguntas.py --preguntas evaluacion/preguntas.json -k 6 --salida evaluacion/resultados_k6.json > run_k6.log 2>&1
echo K6_FIN >> run_k6.log
