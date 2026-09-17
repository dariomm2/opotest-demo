# OpoTest Demo

Demo pública de OpoTest para preparación de oposiciones de bombero. Incluye práctica, Test del día y racha, simulacros, estadísticas y administración con datos sintéticos.

La aplicación está preparada para servirse bajo `/optest/` y convivir con BRUMA, PULSO y NORTE detrás del gateway común de `deploy-demo`.

## Demo

La pantalla de acceso permite entrar directamente como **Alumno** o **Administrador**.

- **Alumno:** inicio, práctica, Test del día, racha, simulacros y estadísticas propias.
- **Administrador:** estadísticas por alumno y generales, gestión de temas, preguntas y usuarios.

La práctica usa **Todas las preguntas** por defecto y los simulacros permiten navegar hacia la pregunta anterior, igual que la aplicación de producción en la revisión fijada por el Dockerfile.

Cada sesión trabaja sobre una copia SQLite temporal privada. Los cambios funcionan durante la sesión, incluido completar el Test del día, pero nunca modifican el dataset común de la demo.

## Datos

Al arrancar se genera automáticamente un dataset reproducible con:

- 20 temas;
- 1.000 preguntas;
- 30 alumnos;
- 2 administradores;
- alrededor de 20.000 respuestas históricas;
- historial de Tests del día y rachas;
- 40 adjuntos de ejemplo.

La actividad cubre los últimos 60 días y sus fechas se desplazan automáticamente al día actual al crear cada sesión. También se desplazan las fechas del historial de Tests del día, por lo que gráficas, heatmaps y rachas no envejecen con el tiempo.

El alumno principal de la demo empieza con una racha de 7 días y el Test del día pendiente, para que esa experiencia pueda probarse directamente.

## Docker

Requiere Docker Engine y Docker Compose.

```bash
docker compose up --build -d
```

La demo queda disponible en:

```text
http://localhost:8000/optest/
```

Para detenerla:

```bash
docker compose down
```

Para eliminar también la SQLite base y regenerar completamente los datos en el siguiente arranque:

```bash
docker compose down -v
```

## Despliegue común

El repositorio está preparado para usarse como directorio hermano de `deploy-demo`:

```text
/demos/
├── deploy/
├── bruma/
├── pulso/
├── norte/
└── optest/
```

El servicio escucha internamente en el puerto `8000`, expone `/health` para el healthcheck y utiliza un volumen en `/data` para la SQLite base.

## Railway (demo individual)

El mismo repositorio puede desplegarse directamente como un único servicio en Railway. Railway detecta el `Dockerfile`; no hace falta desplegar el `gateway` de `docker-compose.yml`.

1. Conecta este repositorio como servicio.
2. Genera un dominio público en **Settings → Networking**.
3. No es necesario definir `PORT`: Railway lo inyecta y el entrypoint lo utiliza automáticamente.
4. Si quieres configurar un healthcheck en Railway, usa `/health`.

Puedes abrir tanto la raíz del dominio como `/optest/`. La aplicación acepta directamente el prefijo `/optest` cuando no existe un proxy que lo retire, y sigue siendo compatible con el gateway común que sí lo retira.

Para esta demo pública no es obligatorio montar un volumen: el dataset se regenera de forma reproducible en cada despliegue y las modificaciones de cada visitante se realizan sobre una SQLite temporal privada. Si se desea conservar la plantilla entre reinicios, puede montarse un Railway Volume en `/data`.

