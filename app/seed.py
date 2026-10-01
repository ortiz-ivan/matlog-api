"""Datos iniciales: turnos de la academia y una biblioteca base de técnicas.

Es idempotente y no pisa cambios hechos desde la app:
- inserta los turnos y técnicas que falten (comparando por nombre);
- en los turnos que ya existen, solo pone el horario semanal si no tienen ninguno;
- en las técnicas que ya existen, solo rellena la descripción si sigue vacía.

Las descripciones son orientativas: los profesores pueden ajustarlas desde la app.
"""

from datetime import time

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Categoria as C
from app.models import Modalidad
from app.models import Posicion as P
from app.models import Tecnica, Turno, TurnoDia

LUNES_A_SABADO = range(6)  # 0 = lunes ... 5 = sábado

# (nombre, inicio, fin, {día de la semana: modalidad})
TURNOS = [
    ("Turno 1", time(19, 30), time(20, 30), {d: Modalidad.GI for d in LUNES_A_SABADO}),
    ("Turno 2", time(20, 30), time(21, 30), {d: Modalidad.GI for d in LUNES_A_SABADO}),
]

# (nombre, categoría, posición, descripción)
TECNICAS: list[tuple[str, C, P, str]] = [
    # --- Guardia cerrada ---
    (
        "Armbar desde guardia cerrada", C.FINALIZACION, P.GUARDIA_CERRADA,
        "Rompe su postura y controla un brazo cruzándolo hacia tu centro. Apoya el pie en su "
        "cadera, gira el cuerpo hasta quedar perpendicular y pasa la pierna por delante de su "
        "cara. Aprieta las rodillas y eleva la cadera con su pulgar apuntando hacia arriba.",
    ),
    (
        "Triángulo desde guardia cerrada", C.FINALIZACION, P.GUARDIA_CERRADA,
        "Deja un brazo del oponente dentro de tus piernas y el otro fuera. Sube la pierna sobre "
        "su nuca y bloquea el tobillo detrás de la otra rodilla. Gira hacia el lado del brazo "
        "atrapado, empújalo cruzando su cuerpo, tira de la cabeza hacia abajo y aprieta las rodillas.",
    ),
    (
        "Omoplata", C.FINALIZACION, P.GUARDIA_CERRADA,
        "Llave de hombro con las piernas. Controla un brazo, gira la cadera hacia fuera y pasa la "
        "pierna por encima de su hombro hasta atraparle el brazo. Siéntate, controla su cintura "
        "para que no ruede hacia delante y lleva tu cadera hacia delante para girar el hombro.",
    ),
    (
        "Kimura desde guardia cerrada", C.FINALIZACION, P.GUARDIA_CERRADA,
        "Cuando apoye una mano en el tatami, agárrale la muñeca, siéntate y pasa tu otro brazo por "
        "encima de su hombro hasta agarrar tu propia muñeca (figura 4). Abre la guardia, gira la "
        "cadera hacia ese lado y lleva su mano hacia su espalda con el codo doblado a 90°.",
    ),
    (
        "Guillotina", C.FINALIZACION, P.GUARDIA_CERRADA,
        "Estrangulación frontal: rodea el cuello con el antebrazo bajo la garganta y junta las "
        "manos. Cierra la guardia, lleva su cabeza contra tu pecho y arquea la espalda subiendo "
        "el antebrazo. Puede hacerse solo al cuello o atrapando también un brazo (arm-in).",
    ),
    (
        "Estrangulación cruzada desde guardia", C.FINALIZACION, P.GUARDIA_CERRADA,
        "Mete la primera mano bien profunda en el cuello de su solapa y la segunda por encima, "
        "en el lado contrario. Atráelo con las piernas para romper su postura y cierra como una "
        "tijera, llevando los codos hacia fuera y hacia abajo. Solo con gi.",
    ),
    (
        "Barrida de tijera", C.BARRIDA, P.GUARDIA_CERRADA,
        "Con agarre de manga y solapa, ponte de lado con una espinilla cruzada en su abdomen y la "
        "otra pierna detrás de su rodilla. Tira de manga y solapa para cargar su peso hacia ti y "
        "cierra las piernas como una tijera: la de abajo corta y la de arriba empuja. Termina en montada.",
    ),
    (
        "Barrida de cadera (hip bump)", C.BARRIDA, P.GUARDIA_CERRADA,
        "Cuando se yergue en tu guardia, siéntate apoyando una mano detrás, abre las piernas y "
        "rodea su hombro con el brazo libre. Empuja la cadera hacia arriba y en diagonal para "
        "volcarlo y termina en montada. Se encadena muy bien con la kimura y la guillotina.",
    ),
    (
        "Barrida de péndulo (flower sweep)", C.BARRIDA, P.GUARDIA_CERRADA,
        "Controla una manga y engancha por debajo su pierna del mismo lado. Abre la guardia, gira "
        "la cadera y balancea la pierna libre como un péndulo para hacerlo caer hacia el lado del "
        "brazo controlado. Sigue el giro hasta la montada.",
    ),
    (
        "Apertura de guardia cerrada de pie", C.PASAJE, P.GUARDIA_CERRADA,
        "Con buena postura y controlando sus solapas o el cinturón contra su abdomen, levántate "
        "primero con un pie y luego con el otro, con la espalda recta y la base ancha. Lleva la "
        "cadera hacia atrás y presiona su muslo hasta que se abran los tobillos.",
    ),
    (
        "Apertura de guardia cerrada de rodillas", C.PASAJE, P.GUARDIA_CERRADA,
        "Con la espalda recta y las manos controlando su cadera, coloca una rodilla en el centro, "
        "bajo su cóccix, y abre la otra pierna hacia atrás para crear ángulo. Empuja su muslo hacia "
        "abajo hasta que se abran los tobillos. Mantén los codos cerrados para evitar armbars y triángulos.",
    ),
    # --- Guardia abierta ---
    (
        "Torreando", C.PASAJE, P.GUARDIA_ABIERTA,
        "Controla el pantalón a la altura de las rodillas, empuja sus piernas hacia un lado contra "
        "el tatami y rodéalas rápido por el otro lado hasta el control lateral. La clave es aplastar "
        "las rodillas y moverse lateralmente antes de que recupere la guardia.",
    ),
    (
        "Knee cut", C.PASAJE, P.GUARDIA_ABIERTA,
        "Corta en diagonal con la rodilla por encima de su muslo hasta apoyarla en el tatami, "
        "controlando su cabeza o un underhook y su brazo del lado por el que pasas. Mantén la cadera "
        "baja y el peso encima hasta llegar al control lateral. Muy útil también contra media guardia.",
    ),
    (
        "Leg drag", C.PASAJE, P.GUARDIA_ABIERTA,
        "Arrastra sus piernas al otro lado de tu cuerpo, cruzando su rodilla por delante de tu "
        "cadera para dejar sus caderas giradas. Pega tu cadera a la suya y avanza al control lateral "
        "o a la espalda sin dejar que vuelva a encuadrarse.",
    ),
    (
        "Pasaje de doble underhook", C.PASAJE, P.GUARDIA_ABIERTA,
        "Mete ambos brazos por debajo de sus muslos y agarra el cinturón o el pantalón. Apila sus "
        "caderas llevándolas hacia su cabeza y, con él doblado, rodea hacia un lado hasta el control "
        "lateral. Cuidado con los triángulos mientras lo apilas.",
    ),
    (
        "Retención de guardia", C.GUARDIA, P.GUARDIA_ABIERTA,
        "Conjunto de recursos para que no te pasen la guardia: mantener marcos con pies, rodillas "
        "y manos entre ambos, mover la cadera para seguirle (camarón) y volver a encuadrar las "
        "piernas. Principio básico: no quedarse con la espalda plana.",
    ),
    (
        "Barrida de mariposa", C.BARRIDA, P.GUARDIA_ABIERTA,
        "Sentado con los ganchos de mariposa por dentro de sus muslos, consigue un underhook y "
        "controla su otro brazo. Déjate caer hacia el lado del brazo controlado y levanta con el "
        "gancho del lado del underhook para volcarlo por encima.",
    ),
    (
        "Barrida de De La Riva", C.BARRIDA, P.GUARDIA_ABIERTA,
        "Desde la guardia De La Riva (gancho por fuera de su pierna adelantada, controlando su "
        "tobillo y una manga o la solapa), rompe su equilibrio empujando con el pie libre en su "
        "cadera o detrás de la otra rodilla mientras sujetas el tobillo. Tiene muchas variantes.",
    ),
    (
        "Barrida de araña (spider)", C.BARRIDA, P.GUARDIA_ABIERTA,
        "Con control de ambas mangas y los pies en sus bíceps, extiende una pierna para "
        "desequilibrarlo y pasa la otra por detrás de su pierna para barrer hacia ese lado. Al tener "
        "las mangas controladas no puede apoyar las manos. Solo con gi.",
    ),
    (
        "Berimbolo", C.TRANSICION, P.GUARDIA_ABIERTA,
        "Desde De La Riva, rueda invertido por encima del hombro manteniendo el gancho y el agarre "
        "del cinturón o el pantalón, girando su cadera hasta llegar a su espalda. Es más una "
        "transición que una barrida y exige practicar el rodamiento invertido.",
    ),
    # --- Media guardia ---
    (
        "Knee shield", C.GUARDIA, P.MEDIA_GUARDIA,
        "Media guardia con la espinilla cruzada entre ambos cuerpos a modo de escudo, para "
        "mantener la distancia y frenar su peso. Combinada con control de manga o un underhook "
        "permite barrer o cambiar a otras guardias. Mantente de lado, nunca con la espalda plana.",
    ),
    (
        "Barrida old school", C.BARRIDA, P.MEDIA_GUARDIA,
        "Desde media guardia, consigue el underhook, ponte de lado y agarra el tobillo de la pierna "
        "que tienes atrapada. Sal por debajo hacia sus rodillas y empuja con el hombro hacia "
        "delante sujetando el tobillo para que no pueda apoyar ese pie. Termina arriba.",
    ),
    (
        "Toma de espalda desde media guardia", C.TRANSICION, P.MEDIA_GUARDIA,
        "Con el underhook, sal de lado sacando la cabeza por debajo de su axila (dogfight), rodea "
        "su espalda con el brazo y pasa detrás colocando los ganchos. Hay que ganar el underhook "
        "antes de que te ponga el crossface.",
    ),
    (
        "Pasaje de media guardia con crossface", C.PASAJE, P.MEDIA_GUARDIA,
        "Arriba en media guardia, aplica el crossface (antebrazo cruzando su cara para girarle la "
        "cabeza) y el underhook del otro lado para aplastarlo plano. Libera la rodilla atrapada "
        "deslizándola o sacando el pie con ayuda del otro, y llega al control lateral o a la montada.",
    ),
    # --- Control lateral ---
    (
        "Kimura desde control lateral", C.FINALIZACION, P.CONTROL_LATERAL,
        "Aísla su brazo lejano llevando la muñeca al tatami, pasa tu otro brazo por debajo de su "
        "brazo y agarra tu propia muñeca (figura 4). Lleva su mano hacia su espalda en un arco "
        "manteniendo su codo pegado a tu cuerpo.",
    ),
    (
        "Americana", C.FINALIZACION, P.CONTROL_LATERAL,
        "Con su mano en el tatami a la altura de la cabeza y el codo doblado a 90°, sujeta su "
        "muñeca y pasa tu otro brazo por debajo de su brazo hasta agarrar tu propia muñeca. "
        "Desliza su mano por el suelo hacia su cadera mientras levantas su codo. También desde montada.",
    ),
    (
        "Transición a montada", C.TRANSICION, P.CONTROL_LATERAL,
        "Desde control lateral, pasa la rodilla por encima de su abdomen hasta el otro lado "
        "manteniendo el control de cabeza y hombros y el peso bajo. Si bloquea con la rodilla, "
        "apártala con la mano o pasa antes por rodilla en el abdomen.",
    ),
    (
        "Rodilla en el abdomen (knee on belly)", C.CONTROL, P.CONTROL_LATERAL,
        "Coloca la espinilla cruzada sobre su abdomen y la otra pierna estirada hacia fuera como "
        "base, controlando solapa y pantalón o cinturón. Sirve para presionar, cambiar de lado y "
        "atacar armbars y estrangulaciones según cómo reaccione.",
    ),
    (
        "Escape de control lateral a guardia", C.ESCAPE, P.CONTROL_LATERAL,
        "Coloca marcos con los antebrazos contra su cuello y su cadera, haz camarón para crear "
        "espacio y mete la rodilla entre ambos para recuperar la guardia. Primero los marcos y "
        "después la cadera: no empujes con los brazos estirados.",
    ),
    # --- Montada ---
    (
        "Armbar desde montada", C.FINALIZACION, P.MONTADA,
        "Desde montada alta, aísla un brazo y apoya la mano en su pecho. Gira hacia ese lado, "
        "siéntate junto a su hombro y pasa la pierna por encima de su cara. Déjate caer hacia atrás "
        "apretando las rodillas y eleva la cadera con su pulgar hacia arriba.",
    ),
    (
        "Estrangulación cruzada desde montada", C.FINALIZACION, P.MONTADA,
        "Mete la primera mano bien profunda en el cuello de su solapa y la segunda en el lado "
        "contrario. Baja el pecho hacia él con los codos abiertos para cerrar la estrangulación, "
        "manteniendo la base con las piernas para que no te voltee. Solo con gi.",
    ),
    (
        "Ezequiel", C.FINALIZACION, P.MONTADA,
        "Pasa un brazo por detrás de su cuello y agarra la manga de tu otro brazo. Mete el canto "
        "de la mano libre por delante de su garganta y cierra juntando los antebrazos. También "
        "funciona desde dentro de la guardia y, sin gi, agarrando la muñeca.",
    ),
    (
        "S-mount", C.CONTROL, P.MONTADA,
        "Montada alta con una rodilla junto a su cabeza y la otra pierna doblada con el pie junto "
        "a su cadera, formando una S. Deja su brazo aislado contra tu cuerpo y es muy fuerte para "
        "atacar el armbar y las estrangulaciones.",
    ),
    (
        "Escape de montada con puente (upa)", C.ESCAPE, P.MONTADA,
        "Atrapa su brazo contra tu pecho y bloquea con tu pie su pie del mismo lado. Haz un puente "
        "alto por encima de tu hombro hacia ese lado y rueda hasta quedar en su guardia. Sin "
        "controlar brazo y pierna del mismo lado, podrá apoyarse y no rodará.",
    ),
    (
        "Escape de montada codo-rodilla", C.ESCAPE, P.MONTADA,
        "Ponte de lado y haz camarón para juntar codo y rodilla y meter la pierna por debajo de la "
        "suya, recuperando media guardia. Repite hacia el otro lado para volver a la guardia "
        "completa. Se combina con el upa según cómo reparta su peso.",
    ),
    # --- Espalda ---
    (
        "Mata león", C.FINALIZACION, P.ESPALDA,
        "Rodea su cuello con el pliegue del codo bajo la barbilla y agarra con esa mano el bíceps "
        "del otro brazo, cuya mano va detrás de su cabeza. Aprieta juntando los codos y abriendo "
        "el pecho. Mantén el control con los ganchos o un triángulo de cuerpo.",
    ),
    (
        "Bow and arrow", C.FINALIZACION, P.ESPALDA,
        "Desde la espalda, mete una mano profunda en el cuello de su solapa y con la otra agarra "
        "su pantalón a la altura de la rodilla contraria. Sal de lado y estira el cuerpo como un "
        "arco, tirando del cuello y empujando la pierna. Solo con gi.",
    ),
    (
        "Control de espalda con ganchos", C.CONTROL, P.ESPALDA,
        "Pecho pegado a su espalda, talones dentro de sus muslos y el cinturón de seguridad "
        "(seatbelt): un brazo por encima del hombro y otro bajo la axila, con las manos juntas. "
        "Mantén tu cabeza junto a la suya y evita caer hacia el lado del brazo de arriba.",
    ),
    (
        "Escape de espalda", C.ESCAPE, P.ESPALDA,
        "Protege primero el cuello controlando el brazo que intenta estrangular. Desliza la espalda "
        "hacia el lado de su brazo de abajo hasta apoyarla en el tatami, quita el gancho de arriba "
        "y gira hacia él para quedar en su guardia o encima.",
    ),
    # --- Norte-sur ---
    (
        "Estrangulación norte-sur", C.FINALIZACION, P.NORTE_SUR,
        "Desde norte-sur, pasa el brazo por debajo de su cuello hasta tener el bíceps contra un "
        "lado y tu pecho contra el otro. Junta las manos, baja la cadera y presiona con el pecho "
        "para cerrar. Funciona con y sin gi.",
    ),
    # --- Tortuga ---
    (
        "Toma de espalda desde tortuga", C.TRANSICION, P.TORTUGA,
        "Colócate a su lado con el pecho sobre su espalda y el seatbelt, mete un gancho entre su "
        "muslo y su codo y rueda de lado para meter el segundo gancho. Lo esencial es no despegar "
        "el pecho de su espalda.",
    ),
    (
        "Clock choke", C.FINALIZACION, P.TORTUGA,
        "Con el oponente en tortuga, mete la mano por debajo y agarra bien profundo el cuello de su "
        "solapa. Carga tu peso sobre su espalda con las piernas abiertas y camina alrededor de su "
        "cabeza como las agujas del reloj mientras aprietas. Solo con gi.",
    ),
    # --- De pie ---
    (
        "Double leg", C.DERRIBO, P.DE_PIE,
        "Baja de nivel y entra con un paso profundo entre sus pies, rodea ambas piernas por detrás "
        "de las rodillas con la cabeza pegada a su costado y empuja o levanta para tumbarlo. "
        "Mantén la espalda recta durante toda la entrada.",
    ),
    (
        "Single leg", C.DERRIBO, P.DE_PIE,
        "Cambia de nivel y captura una pierna con las manos juntas detrás de la rodilla, con la "
        "cabeza pegada a su pecho o costado. Mantén la pierna pegada a tu cadera y termina "
        "empujando en diagonal o con un barrido de la pierna de apoyo.",
    ),
    (
        "O-soto-gari", C.DERRIBO, P.DE_PIE,
        "Proyección de judo: rompe su equilibrio hacia atrás en diagonal, sobre su talón, y entra "
        "a su lado. Siega con tu pierna su pierna del mismo lado por detrás mientras empujas con "
        "el tronco, sin soltar los agarres de manga y solapa.",
    ),
    (
        "Ippon seoi nage", C.DERRIBO, P.DE_PIE,
        "Tira de su manga, gira entrando de espaldas con tu brazo bajo su axila y las rodillas "
        "flexionadas, de forma que tu cadera quede por debajo de la suya. Carga su peso en tu "
        "espalda y proyéctalo por encima del hombro.",
    ),
    (
        "Puxada (pull guard)", C.GUARDIA, P.DE_PIE,
        "Llevar al oponente a tu guardia desde de pie. Con agarres firmes de manga y solapa, "
        "siéntate cerca de él apoyando un pie en su cadera o con un gancho para entrar directo en "
        "tu guardia. Nunca te sientes sin agarres ni lejos de él.",
    ),
]


def _dias(horario: dict[int, Modalidad]) -> list[TurnoDia]:
    return [TurnoDia(dia=dia, modalidad=modalidad) for dia, modalidad in sorted(horario.items())]


def cargar_datos_iniciales(db: Session) -> tuple[int, int, int, int]:
    """Inserta lo que falte y completa horarios y descripciones vacíos.

    Devuelve (turnos creados, horarios completados, técnicas creadas, descripciones añadidas).
    """
    horarios = {nombre.lower(): horario for nombre, _, _, horario in TURNOS}
    turnos_existentes = {t.nombre.lower(): t for t in db.scalars(select(Turno))}
    nuevos_turnos = [
        Turno(nombre=nombre, hora_inicio=inicio, hora_fin=fin, dias=_dias(horario))
        for nombre, inicio, fin, horario in TURNOS
        if nombre.lower() not in turnos_existentes
    ]
    horarios_completados = 0
    for clave, turno in turnos_existentes.items():
        if clave in horarios and not turno.dias:
            turno.dias = _dias(horarios[clave])
            horarios_completados += 1

    descripciones = {nombre.lower(): descripcion for nombre, _, _, descripcion in TECNICAS}
    existentes = {t.nombre.lower(): t for t in db.scalars(select(Tecnica))}

    nuevas_tecnicas = [
        Tecnica(nombre=nombre, categoria=categoria, posicion=posicion, descripcion=descripcion)
        for nombre, categoria, posicion, descripcion in TECNICAS
        if nombre.lower() not in existentes
    ]

    # Solo las que siguen sin descripción: nunca se pisa lo escrito desde la app.
    completadas = 0
    for clave, tecnica in existentes.items():
        if clave in descripciones and not (tecnica.descripcion or "").strip():
            tecnica.descripcion = descripciones[clave]
            completadas += 1

    db.add_all(nuevos_turnos + nuevas_tecnicas)
    db.commit()
    return len(nuevos_turnos), horarios_completados, len(nuevas_tecnicas), completadas
