#!/usr/bin/env python3
"""Generador determinista de datos para OpoTest Demo.

Se ejecuta después de las migraciones Yoyo. Construye una base de demostración
con 20 temas reales de preparación de bomberos, 1.000 preguntas, 30 alumnos,
2 administradores y un historial de estudio progresivo y coherente.

Características del historial simulado:
- los alumnos incorporan los temas por bloques 1-5, 1-10, 1-15 y 1-20;
- los temas antiguos acumulan más práctica que los recién incorporados;
- la probabilidad de acierto aumenta con el número de respuestas acumuladas en
  cada tema, con variaciones de habilidad entre alumnos;
- aparecen práctica, simulacros, fallos y omisiones de forma realista;
- todos los datos se generan con una semilla fija para que la demo sea estable.

Uso manual:
    python demo_seed.py --db /data/app.db
    python demo_seed.py --db /data/app.db --force
"""

from __future__ import annotations

import argparse
import csv
import io
import math
import os
import random
import sqlite3
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Iterable, Sequence

from argon2 import PasswordHasher, Type

SEED_VERSION = "opotest-demo-v14"
DEFAULT_ANCHOR_DATE = date(2026, 8, 31)
RANDOM_SEED = 20260831
PASSWORD_HASHER = PasswordHasher(
    time_cost=2,
    memory_cost=19_456,
    parallelism=1,
    hash_len=32,
    salt_len=16,
    type=Type.ID,
)
QUESTIONS_PER_CONCEPT = 5
EXPECTED_TOPICS = 20
EXPECTED_STUDENTS = 30
EXPECTED_ADMINS = 2
EXPECTED_ATTACHMENTS_PER_TOPIC = 2
EXPECTED_ATTACHMENTS = EXPECTED_TOPICS * EXPECTED_ATTACHMENTS_PER_TOPIC


@dataclass(frozen=True)
class TopicSpec:
    number: str
    name: str
    color: str
    concepts: tuple[tuple[str, str], ...]


TOPICS: tuple[TopicSpec, ...] = (
    TopicSpec("1", "Constitución Española", "#5B7CFA", (
        ("Referéndum constitucional", "La Constitución Española fue ratificada en referéndum el 6 de diciembre de 1978."),
        ("Sanción de la Constitución", "La Constitución fue sancionada por el Rey el 27 de diciembre de 1978."),
        ("Publicación de la Constitución", "La Constitución se publicó en el BOE el 29 de diciembre de 1978 y entró en vigor ese mismo día."),
        ("Artículo 1.1 CE", "España se constituye en un Estado social y democrático de Derecho y proclama como valores superiores la libertad, la justicia, la igualdad y el pluralismo político."),
        ("Artículo 14 CE", "Reconoce la igualdad de los españoles ante la ley y prohíbe la discriminación por las circunstancias que enumera el propio precepto."),
        ("Artículo 15 CE", "Reconoce el derecho a la vida y a la integridad física y moral y prohíbe la tortura y los tratos inhumanos o degradantes."),
        ("Artículo 23 CE", "Reconoce el derecho a participar en los asuntos públicos y a acceder en condiciones de igualdad a las funciones y cargos públicos."),
        ("Artículo 30.4 CE", "Permite que por ley se regulen los deberes de los ciudadanos en los casos de grave riesgo, catástrofe o calamidad pública."),
        ("Artículo 103.1 CE", "La Administración Pública sirve con objetividad los intereses generales y actúa de acuerdo con los principios previstos en la Constitución."),
        ("Artículo 137 CE", "El Estado se organiza territorialmente en municipios, provincias y comunidades autónomas, todas ellas con autonomía para la gestión de sus respectivos intereses."),
    )),
    TopicSpec("2", "Régimen local y administración municipal", "#8B5CF6", (
        ("Municipio", "Es la entidad local básica de la organización territorial del Estado y tiene personalidad jurídica y plena capacidad para el cumplimiento de sus fines."),
        ("Término municipal", "Es el territorio en el que el ayuntamiento ejerce sus competencias."),
        ("Padrón municipal", "Es el registro administrativo donde constan los vecinos de un municipio."),
        ("Ayuntamiento", "El gobierno y la administración municipal corresponden al ayuntamiento, integrado por el alcalde y los concejales, salvo regímenes especiales."),
        ("Pleno municipal", "Está integrado por todos los concejales y es presidido por el alcalde."),
        ("Alcalde", "Preside la corporación, dirige el gobierno y la administración municipal y representa al ayuntamiento, entre otras atribuciones legales."),
        ("Provincia", "Es una entidad local determinada por la agrupación de municipios y una división territorial para el cumplimiento de actividades del Estado."),
        ("Autonomía local", "La Constitución garantiza la autonomía de los municipios para la gestión de sus respectivos intereses."),
        ("Elección de concejales", "Los concejales son elegidos por los vecinos mediante sufragio universal, igual, libre, directo y secreto en los términos de la ley."),
        ("Protección civil e incendios", "La legislación básica de régimen local incluye la protección civil y la prevención y extinción de incendios entre las materias de competencia municipal en los términos legales."),
    )),
    TopicSpec("3", "Empleo público y función pública", "#0EA5E9", (
        ("Funcionario de carrera", "Está vinculado a una Administración Pública por una relación estatutaria regulada por el Derecho Administrativo para el desempeño de servicios profesionales retribuidos de carácter permanente."),
        ("Funcionario interino", "Es nombrado temporalmente por razones expresamente justificadas de necesidad y urgencia para desempeñar funciones propias de funcionarios de carrera en los supuestos legales."),
        ("Personal laboral", "Presta servicios retribuidos para las Administraciones Públicas en virtud de un contrato de trabajo formalizado por escrito."),
        ("Personal eventual", "Realiza funciones expresamente calificadas como de confianza o asesoramiento especial con carácter no permanente."),
        ("Acceso al empleo público", "Debe respetar, entre otros, los principios constitucionales de igualdad, mérito y capacidad, además de la publicidad de las convocatorias."),
        ("Grupo A", "Para acceder a los cuerpos o escalas del grupo A se exige con carácter general estar en posesión de un título universitario de Grado, sin perjuicio de titulaciones específicas exigidas por ley."),
        ("Subgrupo C1", "Para el acceso al subgrupo C1 se exige el título de Bachiller o Técnico."),
        ("Subgrupo C2", "Para el acceso al subgrupo C2 se exige el título de Graduado en Educación Secundaria Obligatoria."),
        ("Código de conducta", "Los empleados públicos deben actuar de acuerdo con principios como objetividad, integridad, neutralidad, responsabilidad, imparcialidad y confidencialidad."),
        ("Formación continua", "La actualización y perfeccionamiento de la cualificación profesional forman parte de los derechos relacionados con la formación de los empleados públicos."),
    )),
    TopicSpec("4", "Prevención de riesgos laborales", "#14B8A6", (
        ("Prevención", "Es el conjunto de actividades o medidas adoptadas o previstas en todas las fases de actividad de la empresa para evitar o disminuir los riesgos derivados del trabajo."),
        ("Riesgo laboral", "Es la posibilidad de que un trabajador sufra un determinado daño derivado del trabajo."),
        ("Daños derivados del trabajo", "Incluyen enfermedades, patologías o lesiones sufridas con motivo u ocasión del trabajo."),
        ("Equipo de protección individual", "Es el equipo destinado a ser llevado o sujetado por el trabajador para protegerle de uno o varios riesgos que puedan amenazar su seguridad o salud."),
        ("Protección colectiva", "Cuando sea técnicamente posible, las medidas de protección colectiva deben anteponerse a la protección individual dentro de los principios preventivos."),
        ("Deber de protección", "El empresario debe garantizar la seguridad y salud de los trabajadores a su servicio en todos los aspectos relacionados con el trabajo."),
        ("Riesgo grave e inminente", "Es aquel que resulte probable racionalmente que se materialice en un futuro inmediato y pueda suponer un daño grave para la salud de los trabajadores."),
        ("Medidas de emergencia", "La organización preventiva debe contemplar primeros auxilios, lucha contra incendios y evacuación de los trabajadores, designando personal y comprobando periódicamente su funcionamiento."),
        ("Formación preventiva", "El trabajador debe recibir una formación teórica y práctica, suficiente y adecuada, centrada específicamente en su puesto o función."),
        ("Obligaciones del trabajador", "El trabajador debe usar adecuadamente máquinas, herramientas, sustancias y equipos de protección y cooperar para que existan condiciones de trabajo seguras."),
    )),
    TopicSpec("5", "Protección civil y gestión de emergencias", "#22C55E", (
        ("Número 112", "Es el número único europeo de emergencias y permite solicitar asistencia urgente de los servicios públicos competentes."),
        ("Protección civil", "Es un servicio público orientado a proteger a las personas y bienes garantizando una respuesta adecuada ante emergencias y catástrofes."),
        ("Planificación de emergencias", "Organiza de forma anticipada recursos, procedimientos, coordinación y actuaciones para responder ante riesgos identificados."),
        ("Autoprotección", "Comprende las medidas que adoptan titulares de actividades, centros o instalaciones para prevenir y controlar riesgos y responder inicialmente a emergencias propias."),
        ("Centro de coordinación", "Centraliza información, comunicaciones y coordinación operativa de los recursos que intervienen en una emergencia."),
        ("Alerta", "Es una comunicación preventiva sobre la posibilidad o evolución de un riesgo para favorecer la preparación antes de que produzca sus efectos."),
        ("Alarma", "Es una señal o aviso que informa de una emergencia real y activa medidas concretas de respuesta o protección."),
        ("Evacuación", "Consiste en trasladar de forma organizada a las personas desde una zona de riesgo hacia otra considerada segura."),
        ("Confinamiento", "Consiste en permanecer en un recinto protegido, reduciendo la exposición al peligro exterior cuando evacuar resulte menos seguro."),
        ("Triaje", "Es la clasificación de víctimas según prioridad asistencial cuando los recursos disponibles deben organizarse frente a múltiples afectados."),
    )),
    TopicSpec("6", "Teoría del fuego", "#F97316", (
        ("Tetraedro del fuego", "Representa combustible, comburente, energía de activación y reacción en cadena como elementos necesarios para mantener una combustión con llama."),
        ("Combustión", "Es una reacción química de oxidación generalmente exotérmica que libera energía en forma de calor y, con frecuencia, luz."),
        ("Punto de inflamación", "Es la temperatura mínima a la que un líquido desprende vapores suficientes para formar una mezcla inflamable que puede encenderse con una fuente externa."),
        ("Temperatura de autoignición", "Es la temperatura mínima a la que una sustancia puede iniciar la combustión sin necesidad de una fuente externa de ignición."),
        ("Pirólisis", "Es la descomposición química de un material por efecto del calor, normalmente con ausencia o escasez de oxígeno, generando productos que pueden ser combustibles."),
        ("Humo", "Es una mezcla de gases, vapores y partículas sólidas o líquidas producidas por la combustión o la pirólisis."),
        ("Llama", "Es la zona gaseosa de una combustión que emite calor y, habitualmente, radiación luminosa."),
        ("Combustión incandescente", "Es una combustión superficial o lenta de un sólido sin llama visible, como puede ocurrir en determinados materiales carbonosos."),
        ("Combustión completa", "Se produce con aporte suficiente de oxígeno y tiende a generar productos más oxidados, como dióxido de carbono y agua en combustibles orgánicos."),
        ("Combustión incompleta", "Se produce con oxidación insuficiente y puede generar monóxido de carbono, hollín y otros productos parcialmente oxidados."),
    )),
    TopicSpec("7", "Propagación y desarrollo del incendio", "#EF4444", (
        ("Conducción", "Es la transferencia de calor a través de un material o entre cuerpos en contacto sin transporte macroscópico de materia."),
        ("Convección", "Es la transferencia de calor asociada al movimiento de un fluido, por ejemplo el ascenso de gases calientes en un incendio."),
        ("Radiación", "Es la transferencia de energía mediante ondas electromagnéticas y no necesita un medio material para propagarse."),
        ("Flashover", "Es la transición rápida a una situación de incendio generalizado en un recinto cuando gran parte de las superficies combustibles se inflaman casi simultáneamente."),
        ("Backdraft", "Es una combustión rápida y potencialmente explosiva que puede producirse al entrar aire en un recinto caliente y pobre en oxígeno con productos de combustión sin quemar."),
        ("Rollover", "Es la aparición de llamas en la capa de gases calientes, normalmente en la parte alta del recinto, antes de que necesariamente se produzca el incendio generalizado."),
        ("Estratificación térmica", "Es la disposición de los gases calientes en capas superiores y del aire relativamente más frío en zonas inferiores de un recinto."),
        ("Plano neutro", "Es la zona aproximada de una abertura donde la diferencia de presión entre interior y exterior cambia de signo, separando flujos de entrada y salida."),
        ("Incendio controlado por ventilación", "Es aquel cuya potencia está limitada principalmente por la cantidad de oxígeno disponible."),
        ("Incendio controlado por combustible", "Es aquel cuya potencia está limitada principalmente por la cantidad y características del combustible que puede arder."),
    )),
    TopicSpec("8", "Agentes extintores y clases de fuego", "#F59E0B", (
        ("Agua", "Su principal mecanismo extintor es la refrigeración gracias a su elevada capacidad para absorber calor."),
        ("Espuma", "Forma una capa sobre determinados combustibles líquidos que ayuda a separar el combustible del aire y a reducir la emisión de vapores."),
        ("Dióxido de carbono", "Es un agente gaseoso que no deja residuo y actúa principalmente reduciendo la concentración de oxígeno en el entorno inmediato del fuego."),
        ("Polvo químico", "Puede interrumpir las reacciones en cadena de la combustión y existen formulaciones adecuadas para distintas clases de fuego."),
        ("Clase A", "Comprende fuegos de materiales sólidos, generalmente de naturaleza orgánica, cuya combustión suele formar brasas."),
        ("Clase B", "Comprende fuegos de líquidos o de sólidos licuables."),
        ("Clase C", "Comprende fuegos de gases."),
        ("Clase D", "Comprende fuegos de metales combustibles."),
        ("Clase F", "Comprende fuegos derivados de la utilización de aceites y grasas para cocinar en aparatos de cocina."),
        ("Riesgo eléctrico", "Antes de aplicar agentes conductores como el agua sobre equipos eléctricos debe eliminarse la tensión o emplearse una técnica y agente adecuados al riesgo eléctrico."),
    )),
    TopicSpec("9", "Hidráulica básica", "#06B6D4", (
        ("Presión", "Es la fuerza ejercida por unidad de superficie."),
        ("Bar", "Un bar equivale exactamente a 100.000 pascales, es decir, 100 kPa."),
        ("Caudal", "Es el volumen de fluido que atraviesa una sección por unidad de tiempo."),
        ("Presión estática", "Es la presión medida en un sistema cuando no existe circulación de agua."),
        ("Presión dinámica o residual", "Es la presión disponible en un punto del sistema mientras existe circulación de agua."),
        ("Pérdida de carga", "Es la disminución de energía o presión producida por rozamiento y singularidades durante el movimiento del agua por una conducción."),
        ("Diámetro de la conducción", "A igualdad de otras condiciones, aumentar el diámetro reduce de forma importante las pérdidas de carga para un mismo caudal."),
        ("Densidad del agua", "A efectos prácticos suele aproximarse a 1.000 kg/m³ en cálculos hidráulicos básicos."),
        ("Cavitación", "Es la formación y posterior colapso de burbujas de vapor cuando la presión local del líquido cae suficientemente, pudiendo dañar una bomba."),
        ("Golpe de ariete", "Es una variación brusca de presión causada por un cambio rápido de la velocidad del agua, por ejemplo al cerrar súbitamente una válvula."),
    )),
    TopicSpec("10", "Mangueras, lanzas y abastecimiento", "#0D9488", (
        ("Manguera contra incendios", "Es una conducción flexible diseñada para transportar agua u otros agentes extintores entre la fuente de suministro y el punto de aplicación."),
        ("Lanza", "Es el dispositivo situado normalmente al final de una línea que permite controlar el caudal y configurar el chorro de agua."),
        ("Chorro compacto", "Concentra el agua en una corriente relativamente sólida, proporcionando normalmente mayor alcance y capacidad de penetración."),
        ("Chorro pulverizado", "Divide el agua en gotas, aumentando la superficie de intercambio térmico y pudiendo crear una pantalla de protección según el patrón empleado."),
        ("Racor", "Es un elemento de conexión que permite unir mangueras y otros componentes hidráulicos compatibles."),
        ("Pliegue o estrangulamiento", "Un pliegue pronunciado en una manguera reduce la sección útil, aumenta las pérdidas y puede limitar el caudal disponible."),
        ("Bifurcación", "Permite dividir una línea de alimentación en dos o más salidas controlables."),
        ("Hidrante", "Es un punto fijo conectado a una red de abastecimiento del que los servicios de extinción pueden obtener agua."),
        ("Columna seca", "Es una instalación fija de tuberías normalmente vacías destinada a que bomberos introduzcan agua desde el exterior y dispongan de tomas en distintas plantas."),
        ("Abastecimiento en serie", "El bombeo en relevo utiliza varias bombas a lo largo de una conducción para mantener caudal y presión en distancias o desniveles importantes."),
    )),
    TopicSpec("11", "Bombas y vehículos de extinción", "#2563EB", (
        ("Bomba centrífuga", "Es el tipo de bomba más habitual en vehículos contra incendios y transforma energía mecánica en energía hidráulica mediante un impulsor giratorio."),
        ("Cebado", "Consiste en evacuar el aire de la aspiración y llenar de agua el cuerpo de bomba y la línea de aspiración para poder aspirar desde una fuente abierta."),
        ("Aspiración", "Para aspirar desde un depósito abierto, la línea situada antes de la bomba debe mantener estanqueidad suficiente para evitar entradas de aire."),
        ("Presión de bomba", "De forma simplificada es el incremento de presión que la bomba aporta entre su entrada y su salida."),
        ("Bombeo en relevo", "Emplea bombas intermedias para compensar pérdidas de carga y desniveles en abastecimientos largos."),
        ("Cavitación en bomba", "Puede aparecer cuando la presión en la aspiración resulta demasiado baja para las condiciones de funcionamiento, produciendo ruido, vibraciones y pérdida de rendimiento."),
        ("Válvula de alivio", "Limita o desvía presión para proteger la instalación frente a sobrepresiones según el sistema de bombeo utilizado."),
        ("Autobomba", "Es un vehículo de bomberos equipado con bomba y material de intervención y, habitualmente, con un depósito de agua de capacidad variable."),
        ("Vehículo de altura", "Dispone de una escalera o brazo aéreo para facilitar acceso, rescate o trabajo a cotas elevadas."),
        ("Dosificador de espuma", "Es el dispositivo que incorpora concentrado espumógeno al agua en una proporción determinada antes de generar la espuma final."),
    )),
    TopicSpec("12", "Equipos de protección individual", "#7C3AED", (
        ("Casco de intervención", "Protege principalmente la cabeza frente a impactos, penetración, calor y otros riesgos dentro de las prestaciones previstas por su diseño y certificación."),
        ("Chaquetón y cubrepantalón", "Constituyen prendas de protección para incendios estructurales con capas destinadas a reducir riesgos térmicos y mecánicos, entre otros."),
        ("Guantes de intervención", "Protegen las manos frente a riesgos térmicos y mecánicos sin eliminar la necesidad de valorar dexteridad y compatibilidad con el resto del equipo."),
        ("Botas de intervención", "Protegen pies y parte inferior de las piernas frente a riesgos mecánicos, térmicos, perforación, deslizamiento y otros previstos por su categoría."),
        ("Capuz de protección", "Cubre zonas de cabeza y cuello que pueden quedar entre la máscara, el casco y las prendas de intervención."),
        ("Selección del EPI", "Debe basarse en la evaluación de riesgos y en la compatibilidad entre los distintos equipos que se usan simultáneamente."),
        ("Inspección previa", "Antes de utilizar un EPI debe comprobarse su estado, limpieza, integridad y correcto funcionamiento conforme a las instrucciones aplicables."),
        ("Mantenimiento del EPI", "Debe realizarse siguiendo las instrucciones del fabricante y los procedimientos del servicio, retirando equipos dañados o fuera de vida útil."),
        ("Control de contaminación", "Separar zonas y materiales limpios de los contaminados reduce la exposición secundaria a productos de combustión y otras sustancias peligrosas."),
        ("Alta visibilidad", "En intervenciones con tráfico rodado pueden ser necesarias prendas de alta visibilidad cuando sean compatibles con los riesgos térmicos y las tareas realizadas."),
    )),
    TopicSpec("13", "Equipos respiratorios y atmósferas peligrosas", "#6366F1", (
        ("ERA autónomo", "Suministra aire respirable desde una botella transportada por el usuario, independientemente de la atmósfera exterior durante su autonomía útil."),
        ("Circuito abierto", "En un equipo respiratorio de circuito abierto, el aire exhalado por el usuario se descarga a la atmósfera en lugar de recircularse."),
        ("Presión positiva", "Mantener una ligera presión positiva dentro de la máscara ayuda a reducir la entrada de contaminantes si existe un pequeño defecto de estanqueidad."),
        ("Manómetro", "Permite conocer la presión disponible en la botella y estimar la reserva de aire junto con el consumo y las características del equipo."),
        ("Alarma de baja presión", "Advierte al usuario cuando la reserva de aire ha alcanzado el umbral establecido por el diseño del equipo."),
        ("Atmósfera IDLH", "Es una atmósfera inmediatamente peligrosa para la vida o la salud, en la que una exposición puede causar efectos graves o impedir la evacuación."),
        ("Deficiencia de oxígeno", "Como referencia de seguridad ampliamente utilizada, una atmósfera con menos del 19,5 % de oxígeno en volumen se considera deficiente en oxígeno."),
        ("Monóxido de carbono", "Es un gas tóxico, incoloro e inodoro que puede generarse en combustiones incompletas."),
        ("Cianuro de hidrógeno", "Es un gas muy tóxico que puede producirse al arder materiales que contienen nitrógeno, incluidos determinados polímeros y fibras."),
        ("Detector multigás", "Debe utilizarse y verificarse conforme a las instrucciones del fabricante, incluyendo las comprobaciones funcionales y calibraciones que correspondan."),
    )),
    TopicSpec("14", "Incendios estructurales", "#DC2626", (
        ("Evaluación inicial", "La evaluación o size-up identifica riesgos, condiciones del incendio, ocupación, recursos y prioridades antes y durante la intervención."),
        ("Búsqueda primaria", "Es una búsqueda rápida orientada a localizar víctimas en las zonas con mayor probabilidad de ocupación mientras se controla el riesgo para los intervinientes."),
        ("Búsqueda secundaria", "Es una revisión más sistemática y exhaustiva realizada cuando las condiciones permiten confirmar que no quedan víctimas."),
        ("Control de puerta", "Gestionar la apertura de una puerta puede limitar la entrada de aire y modificar favorablemente el flujo de gases hasta que la acción esté coordinada."),
        ("Enfriamiento de gases", "La aplicación adecuada de agua pulverizada a la capa caliente puede reducir temperatura y radiación sin sustituir el ataque al combustible que arde."),
        ("Camino de flujo", "Es la trayectoria que siguen gases calientes, humo y aire entre zonas de mayor y menor presión, normalmente desde entradas de aire hacia salidas."),
        ("Estabilidad estructural", "El calor y el incendio pueden reducir la resistencia de elementos estructurales, por lo que deben vigilarse signos de deformación, fallo y colapso."),
        ("Zona de colapso", "Es el área que se mantiene libre alrededor de una estructura o elemento con riesgo de caída para reducir la exposición de intervinientes."),
        ("Ataque ofensivo", "Implica actuar en el interior o muy próximo al foco cuando la evaluación determina que el riesgo es aceptable y existe una estrategia de control interior."),
        ("Ataque defensivo", "Prioriza operaciones desde posiciones exteriores o protegidas cuando las condiciones hacen insegura o injustificada una estrategia interior."),
    )),
    TopicSpec("15", "Ventilación y control de humos", "#E11D48", (
        ("Ventilación", "Es la retirada o desplazamiento controlado de humo, calor y gases de un recinto, normalmente mediante la gestión coordinada de entradas y salidas."),
        ("Ventilación horizontal", "Utiliza aberturas situadas en paredes o cerramientos laterales para establecer el movimiento de gases a través de una planta o recinto."),
        ("Ventilación vertical", "Utiliza una abertura superior, por ejemplo en cubierta, para facilitar la salida de gases calientes cuando la estrategia y la estructura lo permiten."),
        ("Presión positiva", "La ventilación por presión positiva usa un ventilador en una entrada para elevar la presión interior y dirigir los gases hacia una salida previamente definida."),
        ("Presión negativa", "La ventilación por presión negativa utiliza un extractor para retirar gases de un recinto creando una depresión relativa en la zona de extracción."),
        ("Coordinación con extinción", "Abrir o cerrar huecos modifica el aporte de oxígeno y el camino de flujo, por lo que la ventilación debe coordinarse con el ataque al incendio."),
        ("Efecto del viento", "El viento puede dominar el movimiento de gases y aumentar rápidamente las condiciones térmicas en zonas situadas a sotavento dentro del camino de flujo."),
        ("Ventilación hidráulica", "Puede generarse utilizando un chorro pulverizado orientado hacia el exterior de una abertura para arrastrar aire y humo por efecto de inducción."),
        ("Ventilación táctica", "Es la apertura, cierre o uso deliberado de medios mecánicos para modificar las condiciones interiores de acuerdo con un objetivo operativo concreto."),
        ("Ventilación no coordinada", "Una apertura realizada sin coordinación puede incrementar el suministro de oxígeno y acelerar un incendio limitado por ventilación."),
    )),
    TopicSpec("16", "Rescate en accidentes de tráfico", "#EA580C", (
        ("Seguridad de escena", "Antes de la excarcelación deben controlarse tráfico, incendios, derrames, electricidad, estabilidad y otros peligros para víctimas e intervinientes."),
        ("Estabilización del vehículo", "Debe realizarse antes de aplicar fuerzas importantes de corte o separación para evitar movimientos inesperados durante el rescate."),
        ("Sistema de 12 voltios", "Desconectar la batería de baja tensión reduce determinados riesgos, pero no garantiza la desactivación inmediata de todos los sistemas de retención o de alta tensión."),
        ("Airbags", "Los generadores y componentes de airbags no desplegados pueden conservar riesgo, por lo que deben identificarse y respetarse zonas de seguridad durante los trabajos."),
        ("Gestión de cristales", "La retirada o corte de acristalamientos debe planificarse protegiendo a la víctima y al equipo frente a fragmentos, polvo y bordes cortantes."),
        ("Calzos y cribbing", "Se utilizan para crear apoyos estables y controlar movimientos del vehículo durante una excarcelación."),
        ("Separador hidráulico", "Aplica fuerzas de separación o compresión y se utiliza, entre otras tareas, para crear espacio y desplazar componentes deformados."),
        ("Cizalla hidráulica", "Está diseñada para cortar elementos del vehículo compatibles con la capacidad y limitaciones de la herramienta."),
        ("Cilindro de rescate", "Aplica una fuerza lineal de empuje para separar o desplazar componentes y aumentar el espacio disponible."),
        ("Protección de la víctima", "Durante corte, separación y retirada de elementos deben emplearse protecciones físicas y comunicación continua para reducir lesiones secundarias."),
    )),
    TopicSpec("17", "Rescate en altura", "#9333EA", (
        ("Sistema de anclaje", "Es el conjunto de puntos y elementos que transmiten las cargas del sistema de rescate a una estructura con resistencia suficiente."),
        ("Línea principal", "Es la parte del sistema que soporta normalmente la carga del rescatador o la víctima durante una maniobra con cuerdas."),
        ("Línea de seguridad", "Proporciona redundancia frente al fallo de la línea principal cuando el procedimiento y la evaluación de riesgos requieren un sistema asegurado."),
        ("Arnés", "Distribuye las cargas sobre el cuerpo y proporciona puntos de conexión diseñados para las maniobras previstas."),
        ("Mosquetón", "Es un conector con gatillo que debe utilizarse evitando cargas sobre el eje menor, el gatillo o posiciones no previstas por el fabricante."),
        ("Descensor", "Es un dispositivo que permite controlar el desplazamiento descendente de una carga sobre una cuerda compatible."),
        ("Polea", "Cambia la dirección de una cuerda y puede formar parte de sistemas de ventaja mecánica para reducir la fuerza necesaria de tracción."),
        ("Protección de borde", "Evita o reduce daños en cuerdas y cintas producidos por aristas, rozamiento o superficies abrasivas."),
        ("Nudo de ocho", "Es un nudo ampliamente utilizado en trabajos con cuerda para formar gazas o terminaciones cuando el procedimiento lo contempla."),
        ("Síndrome del arnés", "La suspensión inmóvil prolongada puede producir alteraciones graves, por lo que una persona suspendida debe ser rescatada y atendida con rapidez."),
    )),
    TopicSpec("18", "Mercancías peligrosas", "#64748B", (
        ("Número ONU", "Es un número de cuatro cifras asignado a sustancias o artículos peligrosos para facilitar su identificación en el transporte."),
        ("ADR", "Es el acuerdo europeo que regula el transporte internacional de mercancías peligrosas por carretera y sirve de base a la regulación aplicable en los países adheridos."),
        ("Panel naranja", "Es una señalización utilizada en el transporte ADR que puede mostrar números de identificación de peligro y de materia según el tipo de transporte."),
        ("Etiqueta de peligro", "Identifica visualmente la clase o riesgo principal de una mercancía peligrosa mediante símbolos y colores normalizados."),
        ("Zona caliente", "Es el área de mayor contaminación o peligro, con acceso controlado y equipos de protección adecuados al riesgo identificado."),
        ("Zona templada", "Es un área de transición donde suelen situarse operaciones de reducción de contaminación y apoyo controlado entre la zona caliente y la fría."),
        ("Zona fría", "Es el área exterior al peligro inmediato donde se ubican mando, apoyo y recursos que no necesitan entrar en la zona contaminada."),
        ("Descontaminación", "Es el proceso de eliminar, reducir o neutralizar contaminantes presentes sobre personas, equipos o materiales."),
        ("BLEVE", "Es una explosión por expansión de los vapores de un líquido en ebullición cuando falla de forma súbita un recipiente presurizado que contiene líquido por encima de su punto de ebullición atmosférico."),
        ("Ficha de datos de seguridad", "Proporciona información sobre peligros, manipulación, almacenamiento, protección, primeros auxilios y respuesta ante incidentes de una sustancia o mezcla química."),
    )),
    TopicSpec("19", "Incendios forestales", "#16A34A", (
        ("Cabeza del incendio", "Es la zona del perímetro que suele presentar mayor velocidad de propagación y mayor intensidad en la dirección principal de avance."),
        ("Cola del incendio", "Es la zona posterior respecto al avance principal y suele presentar una propagación más lenta que la cabeza."),
        ("Flancos", "Son los laterales del incendio situados entre la cabeza y la cola."),
        ("Focos secundarios", "Se originan cuando pavesas o materiales incandescentes son transportados y encienden combustible separado del perímetro principal."),
        ("Cortafuegos", "Es una discontinuidad del combustible, natural o artificial, que puede utilizarse como apoyo para limitar o controlar la propagación."),
        ("Ataque directo", "Consiste en actuar sobre el borde del incendio o muy próximo a él, extinguiendo o enfriando el combustible que arde y asegurando el perímetro."),
        ("Ataque indirecto", "Se realiza desde una línea de control separada del borde del incendio cuando las condiciones hacen más adecuado trabajar a distancia del frente."),
        ("Pendiente", "En igualdad de otras condiciones, el fuego suele propagarse con mayor rapidez ladera arriba porque las llamas y el calor precalientan el combustible situado por encima."),
        ("Viento", "Aumenta el aporte de oxígeno, inclina la llama, acelera el precalentamiento y puede transportar pavesas, modificando de forma importante la propagación."),
        ("Combustible fino", "Los combustibles de pequeño diámetro intercambian humedad y calor rápidamente, por lo que suelen inflamarse y responder con rapidez a cambios ambientales."),
    )),
    TopicSpec("20", "Primeros auxilios y soporte vital básico", "#DB2777", (
        ("Seguridad de la escena", "Antes de atender a una víctima debe comprobarse que el entorno sea razonablemente seguro para el interviniente, la víctima y terceros."),
        ("Activación del 112", "Ante una emergencia grave debe activarse cuanto antes el sistema de emergencias y seguir las indicaciones del centro coordinador."),
        ("RCP 30:2", "En la reanimación cardiopulmonar básica del adulto, cuando se realizan ventilaciones, se emplea una relación de 30 compresiones por 2 ventilaciones."),
        ("Frecuencia de compresiones", "En el adulto se recomienda una frecuencia aproximada de 100 a 120 compresiones torácicas por minuto."),
        ("Profundidad de compresiones", "En el adulto se busca una profundidad aproximada de 5 a 6 cm, permitiendo la reexpansión completa del tórax entre compresiones."),
        ("DEA", "El desfibrilador externo automatizado analiza el ritmo y solo indica o administra una descarga cuando detecta un ritmo desfibrilable según su algoritmo."),
        ("Posición lateral de seguridad", "Puede utilizarse en una persona inconsciente que respira normalmente cuando no existen circunstancias que obliguen a mantener otra posición y se continúa vigilando la respiración."),
        ("Hemorragia externa grave", "La medida inicial fundamental es aplicar presión directa firme sobre la zona de sangrado, añadiendo otras técnicas de control cuando sean necesarias."),
        ("Quemadura térmica", "Como primera medida se recomienda enfriar la zona con agua corriente fresca durante un periodo prolongado, evitando hielo directo y protegiendo después la lesión."),
        ("Objeto empalado", "No debe retirarse de forma rutinaria un objeto profundamente clavado; se estabiliza y se solicita asistencia sanitaria salvo que una situación excepcional impida actuar de otro modo."),
    )),
)


STUDENT_NAMES: tuple[str, ...] = (
    "Lucía Fernández", "Álvaro Martín", "Marta García", "Diego Alonso", "Sara Prieto",
    "Pablo Santos", "Irene Vega", "Hugo Rodríguez", "Claudia Álvarez", "Javier Blanco",
    "Elena González", "Adrián Ramos", "Nerea Castro", "Marcos Díez", "Paula Iglesias",
    "Daniel Suárez", "Carmen López", "Rubén Herrero", "Laura Pérez", "Sergio Núñez",
    "Andrea Molina", "Mario Gutiérrez", "Noelia Arias", "Víctor Calvo", "Alicia Robles",
    "Óscar Ferrero", "Cristina Méndez", "Guillermo Ortega", "Beatriz Marcos", "Iván Vidal",
)

# Antigüedad de estudio en días. La demo representa aproximadamente dos meses:
# el alumno más veterano empezó hace 60 días y los demás se incorporaron de forma
# escalonada. La distribución mantiene alumnos en las cuatro fases de temario.
STUDY_AGES: tuple[int, ...] = (
    60, 58, 56, 54, 52, 50, 48, 46,
    44, 42, 40, 38, 36, 34, 32,
    30, 28, 26, 24, 22, 20, 19, 18,
    17, 16, 15, 14, 13, 12, 11,
)


def iso(dt: datetime) -> str:
    return dt.astimezone(UTC).isoformat(timespec="milliseconds")


def make_demo_password(username: str) -> str:
    # OpoTest almacena únicamente un hash Argon2id en users.password_hash.
    # La selección Alumno/Administrador de la demo no necesita contraseña, pero
    # generamos hashes plenamente compatibles con el backend real para conservar
    # exactamente el mismo esquema y permitir cualquier flujo interno que valide
    # una contraseña en una copia temporal de la sesión.
    return PASSWORD_HASHER.hash(f"Demo-Only-2026!:{username}")


def weighted_choice(rng: random.Random, items: Sequence[int], weights: Sequence[float]) -> int:
    return rng.choices(items, weights=weights, k=1)[0]


def distinct_distractors(
    rng: random.Random,
    pool: Sequence[str],
    correct: str,
    count: int = 3,
) -> list[str]:
    candidates = [item for item in pool if item != correct]
    if len(candidates) < count:
        raise RuntimeError("No hay suficientes distractores distintos.")
    return rng.sample(candidates, count)


def build_questions_for_topic(rng: random.Random, topic: TopicSpec) -> list[tuple[str, list[str], str, str]]:
    """Devuelve (texto, opciones, correcta, explicación)."""
    concepts = [c for c, _ in topic.concepts]
    definitions = [d for _, d in topic.concepts]
    questions: list[tuple[str, list[str], str, str]] = []

    for concept, definition in topic.concepts:
        concept_distractors = distinct_distractors(rng, concepts, concept)
        definition_distractors = distinct_distractors(rng, definitions, definition)
        explanation = f"{concept}: {definition}"

        variants = [
            (
                f"¿Qué concepto corresponde a esta descripción? {definition}",
                [concept, *concept_distractors],
                concept,
            ),
            (
                f"¿Cuál de las siguientes afirmaciones describe correctamente «{concept}»?",
                [definition, *definition_distractors],
                definition,
            ),
            (
                f"Tema {topic.number}. En relación con «{concept}», señala la opción correcta.",
                [definition, *definition_distractors],
                definition,
            ),
            (
                f"En un test aparece la descripción «{definition}». ¿Qué respuesta marcarías?",
                [concept, *concept_distractors],
                concept,
            ),
            (
                f"¿Qué asociación es correcta dentro de {topic.name}?",
                [
                    f"{concept} — {definition}",
                    *[f"{concept} — {d}" for d in definition_distractors],
                ],
                f"{concept} — {definition}",
            ),
        ]

        for question_text, options, correct in variants:
            rng.shuffle(options)
            questions.append((question_text, options, correct, explanation))

    return questions


def create_meta_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS opotest_demo_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
    )


def current_seed_version(conn: sqlite3.Connection) -> str | None:
    create_meta_table(conn)
    row = conn.execute(
        "SELECT value FROM opotest_demo_meta WHERE key = 'seed_version'"
    ).fetchone()
    return str(row[0]) if row else None


def demo_asset_root() -> Path:
    default = Path(__file__).resolve().parent / "demo_attachments"
    return Path(os.environ.get("OPOTEST_DEMO_ASSET_ROOT", str(default)))


def ensure_demo_attachment_assets() -> dict[int, list[dict[str, object]]]:
    """Crea materiales de ejemplo reales y deterministas para los 20 temas.

    Los archivos viven fuera de SQLite para poder descargarlos desde la demo sin
    S3. Se regeneran en cada arranque: así siguen disponibles aunque la base
    persistente ya estuviera sembrada de una ejecución anterior.
    """
    root = demo_asset_root()
    seed_root = root / "demo-seed"
    seed_root.mkdir(parents=True, exist_ok=True)

    assets: dict[int, list[dict[str, object]]] = {}
    for topic_index, topic in enumerate(TOPICS, start=1):
        topic_dir = seed_root / f"topic-{topic_index:02d}"
        topic_dir.mkdir(parents=True, exist_ok=True)

        summary_name = f"resumen_tema_{topic_index:02d}.txt"
        summary_path = topic_dir / summary_name
        summary_lines = [
            f"OpoTest Demo · Tema {topic.number}: {topic.name}",
            "",
            "Material de ejemplo para la demostración.",
            "",
            "Conceptos clave:",
        ]
        for concept, explanation in topic.concepts:
            summary_lines.append(f"- {concept}: {explanation}")
        summary_lines.extend(["", "Documento generado con datos de demostración.", ""])
        summary_path.write_text("\n".join(summary_lines), encoding="utf-8")

        csv_name = f"conceptos_clave_tema_{topic_index:02d}.csv"
        csv_path = topic_dir / csv_name
        buffer = io.StringIO(newline="")
        writer = csv.writer(buffer)
        writer.writerow(["concepto", "explicacion"])
        writer.writerows(topic.concepts)
        csv_path.write_text(buffer.getvalue(), encoding="utf-8")

        assets[topic_index] = [
            {
                "original_name": f"Resumen Tema {topic.number}.txt",
                "storage_key": f"demo-seed/topic-{topic_index:02d}/{summary_name}",
                "mime_type": "text/plain; charset=utf-8",
                "size_bytes": summary_path.stat().st_size,
                "path": summary_path,
            },
            {
                "original_name": f"Conceptos clave Tema {topic.number}.csv",
                "storage_key": f"demo-seed/topic-{topic_index:02d}/{csv_name}",
                "mime_type": "text/csv; charset=utf-8",
                "size_bytes": csv_path.stat().st_size,
                "path": csv_path,
            },
        ]
    return assets


def insert_topic_attachments(
    conn: sqlite3.Connection,
    topic_ids: Sequence[int],
    assets: dict[int, list[dict[str, object]]],
    anchor: date,
) -> None:
    for topic_index, topic_id in enumerate(topic_ids, start=1):
        block = (topic_index - 1) // 5
        topic_position = (topic_index - 1) % 5
        topic_created = datetime.combine(
            anchor - timedelta(days=60 - block * 15),
            time(0, 10 + topic_position),
            tzinfo=UTC,
        )
        for file_index, asset in enumerate(assets[topic_index], start=1):
            created = topic_created + timedelta(hours=2, minutes=file_index)
            conn.execute(
                """
                INSERT INTO topic_attachments(
                    topic_id, original_name, storage_key, mime_type, size_bytes, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    topic_id,
                    asset["original_name"],
                    asset["storage_key"],
                    asset["mime_type"],
                    asset["size_bytes"],
                    iso(created),
                ),
            )


def database_looks_seeded(conn: sqlite3.Connection) -> bool:
    try:
        counts = {
            "topics": conn.execute("SELECT COUNT(*) FROM topics").fetchone()[0],
            "students": conn.execute("SELECT COUNT(*) FROM users WHERE role='user'").fetchone()[0],
            "admins": conn.execute("SELECT COUNT(*) FROM users WHERE role='admin'").fetchone()[0],
            "questions": conn.execute("SELECT COUNT(*) FROM questions").fetchone()[0],
            "attempts": conn.execute("SELECT COUNT(*) FROM attempts").fetchone()[0],
            "daily_tests": conn.execute("SELECT COUNT(*) FROM daily_tests").fetchone()[0],
            "attachments": conn.execute("SELECT COUNT(*) FROM topic_attachments").fetchone()[0],
        }
    except sqlite3.OperationalError:
        return False
    return (
        counts["topics"] == EXPECTED_TOPICS
        and counts["students"] == EXPECTED_STUDENTS
        and counts["admins"] == EXPECTED_ADMINS
        and counts["questions"] == EXPECTED_TOPICS * 10 * QUESTIONS_PER_CONCEPT
        and counts["attempts"] >= 15_000
        and counts["daily_tests"] >= 80
        and counts["attachments"] == EXPECTED_ATTACHMENTS
    )


def reset_business_data(conn: sqlite3.Connection) -> None:
    # Orden inverso de dependencias. No se tocan las tablas internas de Yoyo.
    for table in (
        "topic_attachment_drafts",
        "topic_attachments",
        "sessions",
        "daily_tests",
        "attempts",
        "user_topics",
        "options",
        "questions",
        "topics",
        "users",
    ):
        conn.execute(f"DELETE FROM {table}")

    try:
        conn.execute(
            "DELETE FROM sqlite_sequence WHERE name IN ('users','topics','questions','options','attempts','sessions','daily_tests','topic_attachments','topic_attachment_drafts')"
        )
    except sqlite3.OperationalError:
        pass


def insert_users(conn: sqlite3.Connection, anchor: date) -> tuple[list[int], list[int]]:
    admin_ids: list[int] = []
    student_ids: list[int] = []

    admins = (
        ("admin_demo", "Coordinación OpoTest"),
        ("admin_apoyo", "Equipo de Formación"),
    )
    for idx, (username, display_name) in enumerate(admins):
        password_hash = make_demo_password(username)
        created = datetime.combine(anchor - timedelta(days=60 - idx * 4), time(9, 0), tzinfo=UTC)
        cur = conn.execute(
            """
            INSERT INTO users(username, display_name, password_hash, role, is_active, created_at, deactivated_at)
            VALUES (?, ?, ?, 'admin', 1, ?, NULL)
            """,
            (username, display_name, password_hash, iso(created)),
        )
        admin_ids.append(int(cur.lastrowid))

    for index, display_name in enumerate(STUDENT_NAMES):
        username = "alumno_demo" if index == 0 else f"alumno{index + 1:02d}"
        password_hash = make_demo_password(username)
        start = anchor - timedelta(days=STUDY_AGES[index])
        created = datetime.combine(start, time(7, 30), tzinfo=UTC)
        cur = conn.execute(
            """
            INSERT INTO users(username, display_name, password_hash, role, is_active, created_at, deactivated_at)
            VALUES (?, ?, ?, 'user', 1, ?, NULL)
            """,
            (username, display_name, password_hash, iso(created)),
        )
        student_ids.append(int(cur.lastrowid))

    return admin_ids, student_ids


def insert_topics_and_questions(
    conn: sqlite3.Connection, rng: random.Random, anchor: date
) -> tuple[list[int], dict[int, list[int]]]:
    topic_ids: list[int] = []
    question_ids_by_topic: dict[int, list[int]] = defaultdict(list)

    for topic_index, topic in enumerate(TOPICS, start=1):
        # Los bloques aparecen cada 15 días. Todas las preguntas del bloque existen antes
        # de la primera sesión de estudio de ese día, evitando actividad anterior a su alta.
        block = (topic_index - 1) // 5
        topic_position = (topic_index - 1) % 5
        topic_created = datetime.combine(
            anchor - timedelta(days=60 - block * 15),
            time(0, 10 + topic_position),
            tzinfo=UTC,
        )
        topic_cur = conn.execute(
            "INSERT INTO topics(number, name, color, created_at) VALUES (?, ?, ?, ?)",
            (topic.number, topic.name, topic.color, iso(topic_created)),
        )
        topic_id = int(topic_cur.lastrowid)
        topic_ids.append(topic_id)

        generated = build_questions_for_topic(rng, topic)
        for q_index, (text_, options, correct, explanation) in enumerate(generated):
            created = topic_created + timedelta(minutes=q_index + 1)
            q_cur = conn.execute(
                """
                INSERT INTO questions(topic_id, text, explanation, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (topic_id, text_, explanation, iso(created), iso(created)),
            )
            question_id = int(q_cur.lastrowid)
            question_ids_by_topic[topic_id].append(question_id)

            for position, option_text in enumerate(options):
                conn.execute(
                    "INSERT INTO options(question_id, text, position, is_correct) VALUES (?, ?, ?, ?)",
                    (question_id, option_text, position, 1 if option_text == correct else 0),
                )

    return topic_ids, question_ids_by_topic


def stage_topic_count(days_since_start: int) -> int:
    # Dos meses de preparación, incorporando un bloque nuevo aproximadamente cada 15 días.
    if days_since_start < 15:
        return 5
    if days_since_start < 30:
        return 10
    if days_since_start < 45:
        return 15
    return 20


def study_probability(student_index: int, current_day: date) -> float:
    # Constancia razonablemente alta, con diferencias personales pequeñas y fin de semana algo más activo.
    dedication = 0.61 + (student_index % 6) * 0.035
    weekend_bonus = 0.06 if current_day.weekday() >= 5 else 0.0
    return min(0.90, dedication + weekend_bonus)


def attempts_for_study_day(rng: random.Random, student_index: int, days_since_start: int) -> int:
    # En dos meses la carga aumenta de forma gradual sin jornadas desproporcionadas.
    maturity = min(1.0, days_since_start / 50)
    base = 18 + (student_index % 5) * 2
    extra = int(10 * maturity)
    count = int(rng.triangular(max(12, base - 5), base + extra + 14, base + extra + 2))
    if rng.random() < 0.05:
        count += rng.randint(10, 24)
    return max(12, min(count, 58))


def topic_correct_probability(
    student_index: int,
    topic_attempts: int,
    topic_number: int,
    days_since_start: int,
) -> float:
    # La habilidad sube suavemente con la práctica del propio tema y con la experiencia general.
    # Los temas nuevos arrancan algo por debajo, pero no provocan caídas bruscas en la curva global.
    base_skill = 0.515 + (student_index % 8) * 0.008
    topic_learning = 0.255 * (1.0 - math.exp(-topic_attempts / 90.0))
    general_learning = 0.075 * (1.0 - math.exp(-days_since_start / 28.0))
    difficulty_penalty = ((topic_number * 7) % 5) * 0.006
    return max(0.49, min(0.91, base_skill + topic_learning + general_learning - difficulty_penalty))


@dataclass
class OutcomeBalancer:
    """Acumuladores de error para generar resultados suaves sin volverlos perfectos."""

    correct_credit: float
    skip_credit: float


def stable_outcome(
    student_index: int,
    answer_index: int,
    correct_probability: float,
    skip_probability: float,
    topic_number: int,
    balance: OutcomeBalancer,
) -> str:
    """Genera un resultado estable alrededor de la probabilidad objetivo.

    En vez de lanzar una Bernoulli independiente para cada pregunta, acumula la
    probabilidad como un distribuidor de error. De este modo las ventanas móviles de
    30 respuestas (las que usa OpoTest en el gráfico de acierto) siguen la tendencia
    de aprendizaje y no dibujan dientes de sierra artificiales. Se añade una oscilación
    pequeña y lenta para que el historial continúe pareciendo humano.
    """
    balance.skip_credit += skip_probability
    if balance.skip_credit >= 1.0:
        balance.skip_credit -= 1.0
        return "skipped"

    form = (
        0.010 * math.sin((answer_index + student_index * 13) / 29.0)
        + 0.005 * math.sin((answer_index + topic_number * 17) / 11.0)
    )
    target = max(0.47, min(0.92, correct_probability + form))
    balance.correct_credit += target
    if balance.correct_credit >= 1.0:
        balance.correct_credit -= 1.0
        return "correct"
    return "incorrect"


def choose_topic_for_attempt(
    rng: random.Random,
    active_topic_ids: Sequence[int],
    attempts_by_topic: dict[int, int],
) -> int:
    # Los recién incorporados reciben atención, pero los temas anteriores siguen repasándose.
    max_seen = max(attempts_by_topic.get(topic_id, 0) for topic_id in active_topic_ids) if active_topic_ids else 0
    weights: list[float] = []
    for position, topic_id in enumerate(active_topic_ids):
        seen = attempts_by_topic.get(topic_id, 0)
        freshness = 1.0 + 0.22 * (position / max(1, len(active_topic_ids) - 1))
        undertrained = 1.0 + 0.34 * ((max_seen - seen) / max(1, max_seen + 1))
        weights.append(freshness * undertrained)
    return weighted_choice(rng, list(active_topic_ids), weights)

def insert_user_topics(conn: sqlite3.Connection, student_ids: Sequence[int], topic_ids: Sequence[int]) -> None:
    for idx, user_id in enumerate(student_ids):
        current_stage = stage_topic_count(STUDY_AGES[idx])
        conn.executemany(
            "INSERT INTO user_topics(user_id, topic_id) VALUES (?, ?)",
            [(user_id, topic_id) for topic_id in topic_ids[:current_stage]],
        )


def insert_attempt_history(
    conn: sqlite3.Connection,
    rng: random.Random,
    anchor: date,
    student_ids: Sequence[int],
    topic_ids: Sequence[int],
    question_ids_by_topic: dict[int, list[int]],
) -> int:
    rows: list[tuple[int, int, str, str, str, str]] = []
    submission_counter = 0

    for student_index, user_id in enumerate(student_ids):
        age = STUDY_AGES[student_index]
        start_date = anchor - timedelta(days=age)
        attempts_by_topic: dict[int, int] = defaultdict(int)
        student_answer_index = 0
        outcome_balance = OutcomeBalancer(
            correct_credit=(0.37 + student_index * 0.173) % 1.0,
            skip_credit=(0.61 + student_index * 0.211) % 1.0,
        )
        last_activity_day: date | None = None

        for day_offset in range(age + 1):
            current_day = start_date + timedelta(days=day_offset)
            if rng.random() > study_probability(student_index, current_day):
                continue

            active_count = stage_topic_count(day_offset)
            active_topic_ids = topic_ids[:active_count]
            day_attempts = attempts_for_study_day(rng, student_index, day_offset)

            morning_session = rng.random() < 0.20
            base_hour = rng.randint(8, 11) if morning_session else rng.randint(17, 20)
            minute_cursor = rng.randint(0, 18)

            for _ in range(day_attempts):
                topic_id = choose_topic_for_attempt(rng, active_topic_ids, attempts_by_topic)
                topic_number = topic_ids.index(topic_id) + 1
                question_id = rng.choice(question_ids_by_topic[topic_id])

                seen = attempts_by_topic[topic_id]
                correct_probability = topic_correct_probability(
                    student_index, seen, topic_number, day_offset
                )
                skip_probability = max(0.008, 0.032 - min(seen, 180) * 0.00010)
                outcome = stable_outcome(
                    student_index,
                    student_answer_index,
                    correct_probability,
                    skip_probability,
                    topic_number,
                    outcome_balance,
                )
                student_answer_index += 1

                # Los simulacros van ganando peso de forma gradual a lo largo de los dos meses.
                simulation_probability = 0.05 + 0.23 * min(1.0, day_offset / 55)
                source = "simulation" if rng.random() < simulation_probability else "practice"

                minute_cursor += rng.randint(1, 3)
                attempt_time = datetime.combine(current_day, time(base_hour, 0), tzinfo=UTC) + timedelta(
                    minutes=minute_cursor
                )
                if attempt_time.hour >= 23:
                    attempt_time = datetime.combine(current_day, time(21, 0), tzinfo=UTC) + timedelta(
                        minutes=rng.randint(0, 90)
                    )

                submission_counter += 1
                submission_key = f"demo-v10-{user_id}-{submission_counter:07d}"
                rows.append((user_id, question_id, outcome, source, submission_key, iso(attempt_time)))
                attempts_by_topic[topic_id] += 1
                last_activity_day = current_day

        # Garantiza actividad reciente solo cuando el azar dejó al alumno sin estudiar en los últimos 4 días.
        if age >= 7 and (last_activity_day is None or (anchor - last_activity_day).days > 4):
            current_day = anchor - timedelta(days=2 + student_index % 2)
            elapsed = max(0, age - (anchor - current_day).days)
            active_topic_ids = topic_ids[: stage_topic_count(elapsed)]
            for _ in range(14 + student_index % 5):
                topic_id = choose_topic_for_attempt(rng, active_topic_ids, attempts_by_topic)
                topic_number = topic_ids.index(topic_id) + 1
                question_id = rng.choice(question_ids_by_topic[topic_id])
                seen = attempts_by_topic[topic_id]
                p = topic_correct_probability(student_index, seen, topic_number, elapsed)
                outcome = stable_outcome(
                    student_index,
                    student_answer_index,
                    p,
                    max(0.008, 0.026 - min(seen, 180) * 0.00008),
                    topic_number,
                    outcome_balance,
                )
                student_answer_index += 1
                source = "simulation" if rng.random() < 0.24 else "practice"
                submission_counter += 1
                attempt_time = datetime.combine(
                    current_day, time(18 + (student_index % 3), rng.randint(0, 59)), tzinfo=UTC
                )
                rows.append(
                    (
                        user_id,
                        question_id,
                        outcome,
                        source,
                        f"demo-v10-{user_id}-{submission_counter:07d}",
                        iso(attempt_time),
                    )
                )
                attempts_by_topic[topic_id] += 1

    rows.sort(key=lambda row: row[-1])
    conn.executemany(
        """
        INSERT INTO attempts(user_id, question_id, outcome, source, submission_key, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        rows,
    )
    return len(rows)

def insert_daily_test_history(
    conn: sqlite3.Connection,
    anchor: date,
    student_ids: Sequence[int],
) -> int:
    """Crea rachas recientes y variadas para el Test del día.

    alumno_demo termina ayer con una racha de 7 días: al entrar hoy verá la racha
    activa pendiente y podrá completarla. Otros alumnos mezclan estados completado,
    pendiente e inactivo para que las estadísticas administrativas resulten naturales.
    """
    rows: set[tuple[int, str]] = set()
    for index, user_id in enumerate(student_ids):
        age = STUDY_AGES[index]
        start = anchor - timedelta(days=age)

        if index == 0:
            streak = 7
            end_day = anchor - timedelta(days=1)
        elif index % 7 == 0:
            # Algunos alumnos no han consolidado todavía una racha.
            continue
        else:
            streak = 2 + ((index * 3) % 9)
            # Repartimos alumnos entre test ya hecho hoy y test pendiente.
            end_day = anchor if index % 4 == 0 else anchor - timedelta(days=1)

        first_day = max(start, end_day - timedelta(days=streak - 1))
        day = first_day
        while day <= end_day:
            rows.add((user_id, day.isoformat()))
            day += timedelta(days=1)

        # Algún test aislado anterior rompe la monotonía y hace el historial más humano,
        # sin alterar la racha vigente que calcula el backend.
        if age >= 24 and index % 3 == 1:
            isolated = end_day - timedelta(days=streak + 4 + index % 4)
            if isolated >= start:
                rows.add((user_id, isolated.isoformat()))

    ordered = sorted(rows, key=lambda row: (row[1], row[0]))
    conn.executemany(
        "INSERT INTO daily_tests(user_id, completed_on) VALUES (?, ?)",
        ordered,
    )
    return len(ordered)

def validate_seed(conn: sqlite3.Connection) -> dict[str, int | float]:
    counts = {
        "topics": int(conn.execute("SELECT COUNT(*) FROM topics").fetchone()[0]),
        "questions": int(conn.execute("SELECT COUNT(*) FROM questions").fetchone()[0]),
        "options": int(conn.execute("SELECT COUNT(*) FROM options").fetchone()[0]),
        "students": int(conn.execute("SELECT COUNT(*) FROM users WHERE role='user'").fetchone()[0]),
        "admins": int(conn.execute("SELECT COUNT(*) FROM users WHERE role='admin'").fetchone()[0]),
        "attempts": int(conn.execute("SELECT COUNT(*) FROM attempts").fetchone()[0]),
        "daily_tests": int(conn.execute("SELECT COUNT(*) FROM daily_tests").fetchone()[0]),
        "user_topics": int(conn.execute("SELECT COUNT(*) FROM user_topics").fetchone()[0]),
        "attachments": int(conn.execute("SELECT COUNT(*) FROM topic_attachments").fetchone()[0]),
    }
    if counts["topics"] != EXPECTED_TOPICS:
        raise RuntimeError(f"Seed inválido: {counts['topics']} temas.")
    if counts["questions"] != EXPECTED_TOPICS * 10 * QUESTIONS_PER_CONCEPT:
        raise RuntimeError(f"Seed inválido: {counts['questions']} preguntas.")
    if counts["options"] != counts["questions"] * 4:
        raise RuntimeError(f"Seed inválido: {counts['options']} opciones.")
    if counts["students"] != EXPECTED_STUDENTS or counts["admins"] != EXPECTED_ADMINS:
        raise RuntimeError("Seed inválido: número de usuarios incorrecto.")
    if counts["attempts"] < 15_000:
        raise RuntimeError("Seed inválido: historial insuficiente.")
    if counts["daily_tests"] < 80:
        raise RuntimeError("Seed inválido: historial de Test del día insuficiente.")
    if counts["attachments"] != EXPECTED_ATTACHMENTS:
        raise RuntimeError(f"Seed inválido: {counts['attachments']} adjuntos de tema.")

    invalid_attachment_distribution = conn.execute(
        """
        SELECT COUNT(*) FROM (
          SELECT t.id, COUNT(a.id) AS attachment_count
          FROM topics t
          LEFT JOIN topic_attachments a ON a.topic_id=t.id
          GROUP BY t.id
          HAVING attachment_count != ?
        )
        """,
        (EXPECTED_ATTACHMENTS_PER_TOPIC,),
    ).fetchone()[0]
    if invalid_attachment_distribution:
        raise RuntimeError(
            f"Seed inválido: {invalid_attachment_distribution} temas no tienen exactamente "
            f"{EXPECTED_ATTACHMENTS_PER_TOPIC} adjuntos."
        )

    invalid_questions = conn.execute(
        """
        SELECT COUNT(*) FROM (
          SELECT q.id, SUM(CASE WHEN o.is_correct=1 THEN 1 ELSE 0 END) AS correct_count, COUNT(o.id) AS option_count
          FROM questions q JOIN options o ON o.question_id=q.id
          GROUP BY q.id
          HAVING correct_count != 1 OR option_count != 4
        )
        """
    ).fetchone()[0]
    if invalid_questions:
        raise RuntimeError(f"Seed inválido: {invalid_questions} preguntas con opciones incorrectas.")

    invalid_chronology = conn.execute(
        """
        SELECT COUNT(*)
        FROM attempts a
        JOIN questions q ON q.id=a.question_id
        JOIN users u ON u.id=a.user_id
        WHERE a.created_at < q.created_at OR a.created_at < u.created_at
        """
    ).fetchone()[0]
    if invalid_chronology:
        raise RuntimeError(
            f"Seed inválido: {invalid_chronology} respuestas anteriores al alta de su usuario o pregunta."
        )

    demo_user = conn.execute("SELECT id FROM users WHERE username='alumno_demo'").fetchone()
    if demo_user is None:
        raise RuntimeError("Seed inválido: falta alumno_demo.")
    user_id = int(demo_user[0])
    anchor_row = conn.execute("SELECT value FROM opotest_demo_meta WHERE key='seed_anchor_date'").fetchone()
    validation_anchor = date.fromisoformat(anchor_row[0]) if anchor_row else DEFAULT_ANCHOR_DATE
    demo_daily = [
        row[0] for row in conn.execute(
            "SELECT completed_on FROM daily_tests WHERE user_id=? ORDER BY completed_on DESC LIMIT 7",
            (user_id,),
        ).fetchall()
    ]
    expected_daily = [(validation_anchor - timedelta(days=offset)).isoformat() for offset in range(1, 8)]
    if demo_daily != expected_daily:
        raise RuntimeError("Seed inválido: alumno_demo debe arrancar con una racha pendiente de 7 días.")
    topic_stats = conn.execute(
        """
        SELECT t.id,
               COUNT(a.id) AS attempts,
               AVG(CASE WHEN a.outcome='correct' THEN 1.0 WHEN a.outcome='incorrect' THEN 0.0 END) AS accuracy
        FROM topics t
        LEFT JOIN questions q ON q.topic_id=t.id
        LEFT JOIN attempts a ON a.question_id=q.id AND a.user_id=?
        GROUP BY t.id ORDER BY t.id
        """,
        (user_id,),
    ).fetchall()
    first_attempts = sum(int(row[1]) for row in topic_stats[:5])
    last_attempts = sum(int(row[1]) for row in topic_stats[-5:])
    first_accuracy = sum(float(row[2] or 0) for row in topic_stats[:5]) / 5
    last_accuracy = sum(float(row[2] or 0) for row in topic_stats[-5:]) / 5
    if first_attempts <= last_attempts:
        raise RuntimeError("Seed poco realista: el alumno demo no ha practicado más los temas antiguos.")
    if first_accuracy <= last_accuracy:
        raise RuntimeError("Seed poco realista: la curva de aprendizaje no mejora los temas más practicados.")

    counts["demo_first5_accuracy"] = round(first_accuracy * 100, 1)
    counts["demo_last5_accuracy"] = round(last_accuracy * 100, 1)
    return counts


def seed_database(db_path: Path, *, force: bool = False, anchor: date | None = None) -> dict[str, int | float]:
    anchor = anchor or DEFAULT_ANCHOR_DATE
    db_path.parent.mkdir(parents=True, exist_ok=True)
    assets = ensure_demo_attachment_assets()
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA journal_mode=WAL")
    try:
        existing_version = current_seed_version(conn)
        if not force and existing_version == SEED_VERSION and database_looks_seeded(conn):
            return validate_seed(conn)

        rng = random.Random(RANDOM_SEED)
        with conn:
            reset_business_data(conn)
            _, student_ids = insert_users(conn, anchor)
            topic_ids, question_ids_by_topic = insert_topics_and_questions(conn, rng, anchor)
            insert_topic_attachments(conn, topic_ids, assets, anchor)
            insert_user_topics(conn, student_ids, topic_ids)
            insert_attempt_history(conn, rng, anchor, student_ids, topic_ids, question_ids_by_topic)
            insert_daily_test_history(conn, anchor, student_ids)
            create_meta_table(conn)
            conn.execute(
                "INSERT INTO opotest_demo_meta(key, value) VALUES('seed_version', ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (SEED_VERSION,),
            )
            conn.execute(
                "INSERT INTO opotest_demo_meta(key, value) VALUES('seed_anchor_date', ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (anchor.isoformat(),),
            )

        return validate_seed(conn)
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Genera la base realista de OpoTest Demo")
    parser.add_argument("--db", default=os.environ.get("OPOTEST_DB_PATH", "/data/app.db"))
    parser.add_argument("--force", action="store_true", help="Regenera aunque ya exista la versión actual")
    parser.add_argument(
        "--anchor-date",
        default=os.environ.get("OPOTEST_DEMO_SEED_DATE"),
        help=f"Fecha de referencia YYYY-MM-DD. Por defecto {DEFAULT_ANCHOR_DATE.isoformat()} (las sesiones se desplazan a hoy).",
    )
    args = parser.parse_args()
    anchor = date.fromisoformat(args.anchor_date) if args.anchor_date else None
    stats = seed_database(Path(args.db), force=args.force, anchor=anchor)
    print(
        "OpoTest Demo seed listo: "
        f"{stats['topics']} temas, {stats['questions']} preguntas, "
        f"{stats['students']} alumnos, {stats['admins']} admins, {stats['attachments']} adjuntos, "
        f"{stats['attempts']} respuestas y {stats['daily_tests']} tests diarios completados."
    )
    print(
        "Alumno demo: precisión media temas 1-5 "
        f"{stats['demo_first5_accuracy']}% vs temas 16-20 {stats['demo_last5_accuracy']}%."
    )


if __name__ == "__main__":
    main()
