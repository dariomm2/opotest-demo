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
