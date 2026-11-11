BEGIN;

-- Opcional: Limpia las tablas y reinicia los contadores de ID a 1 por si re-ejecutas el script
TRUNCATE TABLE 
    perfil, 
    experiencia, 
    proyectos, 
    tecnologias, 
    idiomas, 
    educacion,
    documentos_rag,
    chunks_rag
RESTART IDENTITY CASCADE;

-- ==========================================
-- 1. PERFIL (Generará id = 1)
-- ==========================================
INSERT INTO perfil (nombre_completo, titular, biografia, ubicacion, email, github_url, linkedin_url, web_personal)
VALUES (
    'Ander Aquerreta Montoro',
    'Data Scientist & AI Engineer',
    'Ingeniero de IA y Científico de Datos especializado en el diseño y despliegue de arquitecturas RAG, orquestación de agentes y pipelines MLOps sobre infraestructura propia.',
    'Almansa, España',
    'anderaquerretamontoro@gmail.com', -- Ajusta tu email de contacto
    'https://github.com/aaquerrmon',
    'https://linkedin.com/in/ander-aquerreta-montoro', -- Ajusta tu URL exacta de LinkedIn
    'https://anderaquerreta.com'
);

-- ==========================================
-- 2. EXPERIENCIA LABORAL
-- ==========================================
INSERT INTO experiencia (empresa, rol, tipo_contrato, fecha_inicio, fecha_fin, descripcion, perfil_id)
VALUES (
    'Universidad Politécnica de Valencia (UPV)',
    'AI Engineer',
    'Tiempo completo',
    '2024-10-31', -- Ajusta la fecha exacta de inicio
    NULL,         -- NULL indica puesto actual
    'Desarrollo y despliegue de infraestructura y servicios de Inteligencia Artificial para la universidad. Creación de sistemas multi-agente y RAG (PoliAgentes) y sistemas de recomendación y búsqueda semántica para MediaUPV (PoliRecommender / BuscadorIA).',
    1
),
(
    'Universidad Politécnica de Valencia (UPV)',
    'AI Engineer',
    'Prácticas',
    '2024-03-01',
    '2024-09-30',
    'Traducción de lenguaje de signos a texto mediante modelos de visión artificial.',
    1
),
(
    'Hospital Universitario de Navarra (HUN)',
    'Data Scientist',
    'Prácticas',
    '2022-09-01',
    '2022-12-31',
    'Análisis de datos médicos y desarrollo de modelos de minería de procesos para optimizar la gestión hospitalaria.',
    1
),
(
    'Stats Perform',
    'Data Collector',
    'Tiempo parcial',
    '2026-01-01',
    NULL,
    'Recolección de datos en partidos de fútbol profesional',
    1
);
;

-- ==========================================
-- 3. PROYECTOS DESTACADOS
-- ==========================================
INSERT INTO proyectos (titulo, descripcion_completa, tipo, url_publica, destacado, perfil_id)
VALUES 
(
    'PoliAgentes',
    'Plataforma universitaria de gestión multi-agente y recuperación de conocimiento basada en arquitecturas RAG para consulta de normativa y documentación interna.',
    'Investigación UPV',
    NULL,
    TRUE,
    1
),
(
    'PoliEscaner',
    'Servicio de extracción automática de texto y estructuración documental combinando motores de OCR (Docling, RapidOCR, DeepSeekOCR) acelerados por GPU.',
    'Investigación UPV',
    NULL,
    TRUE,
    1
),
(
    'PoliEmbeddings & BuscadorIA (MediaUPV)',
    'Infraestructura centralizada de generación de embeddings en GPU y buscador/recomendador semántico para el catálogo de vídeos académicos de MediaUPV.',
    'Investigación UPV',
    NULL,
    TRUE,
    1
),
(
    'Node2Agents',
    'Proyecto open-source para la creación, conexión y orquestación modular de agentes de IA.',
    'Open Source',
    'https://github.com/aaquerrmon/Node2Agents',
    FALSE,
    1
),
(
    'Portfolio Personal',
    'Web personal desarrollada con Astro, Tailwind CSS y desplegada en Cloudflare Pages, respaldada por PostgreSQL + pgvector para consultas semánticas sobre experiencia y proyectos.',
    'Proyecto Personal',
    'https://anderaquerreta.com',
    TRUE,
    1
),
(
    'Trabajo de fin de Grado (TFG)',
    'Mejora de la eficiencia de las listas de espera mediante minería de procesos y aprendizaje automático',
    'Trabajo de Fin de Grado',
    'https://academica-e.unavarra.es/entities/publication/f29f3278-eccf-431d-9480-0b0ba4adfab1',
    TRUE,
    1
),
(
    'Trabajo de fin de Máster (TFM)',
    'Sistema de traducción automática de lengua de signos a texto mediante visión artificial y aprendizaje profundo.',
    'Trabajo de Fin de Máster',
    'https://riunet.upv.es/entities/person/35d70e0e-bb4d-491e-b5b9-d5cbeb0a1c38',
    TRUE,
    1
);

-- ==========================================
-- 4. TECNOLOGÍAS (STACK TECNOLÓGICO)
-- ==========================================
INSERT INTO tecnologias (nombre, categoria, nivel, perfil_id)
VALUES 
    -- Lenguajes & Backend
    ('Python', 'Backend & Data Science', 'Avanzado', 1),
    ('FastAPI', 'Backend', 'Avanzado', 1),
    ('SQL', 'Bases de Datos', 'Avanzado', 1),
    ('Javascript', 'Frontend', 'Intermedio', 1),
    ('Java', 'Backend', 'Basico', 1),
    
    -- IA, LLMs & Datos
    ('vLLM', 'Machine Learning / IA', 'Avanzado', 1),
    ('Ollama', 'Machine Learning / IA', 'Avanzado', 1),
    ('Arquitecturas RAG', 'Machine Learning / IA', 'Avanzado', 1),
    ('MCP (Model Context Protocol)', 'Machine Learning / IA', 'Avanzado', 1),
    ('Docling', 'Machine Learning / IA', 'Avanzado', 1),
    ('Ragas', 'Machine Learning / IA', 'Intermedio', 1),
    ('LightGBM / Scikit-Learn', 'Machine Learning / IA', 'Avanzado', 1),

    -- Bases de Datos & Vector Stores
    ('Oracle', 'Bases de Datos', 'Avanzado', 1),
    ('PostgreSQL & pgvector', 'Bases de Datos', 'Avanzado', 1),
    ('Milvus', 'Bases de Datos', 'Avanzado', 1),

    -- DevOps & Infraestructura
    ('Docker & Docker Compose', 'DevOps', 'Avanzado', 1),
    ('Linux (CachyOS, Ubuntu, Fedora)', 'Sistemas', 'Avanzado', 1),
    ('Nginx', 'DevOps', 'Intermedio', 1),
    ('uv', 'Herramientas Python', 'Avanzado', 1),
    ('Git & GitHub', 'Control de Versiones', 'Avanzado', 1),

    -- Frontend & Visualización
    ('Astro', 'Frontend', 'Intermedio', 1),
    ('Tailwind CSS & DaisyUI', 'Frontend', 'Intermedio', 1),
    ('Streamlit & Plotly', 'Data Visualization', 'Avanzado', 1);

-- ==========================================
-- 5. EDUCACIÓN
-- ==========================================
INSERT INTO educacion (titulo, institucion, fecha_inicio, fecha_fin, detalles, perfil_id)
VALUES (
    'Grado en Ciencia de Datos (B.Sc. in Data Science)',
    'Universidad Pública de Navarra (UPNA)',
    '2019-09-01',
    '2023-06-30',
    'Formación especializada en estadística, aprendizaje automático, ingeniería de datos, optimización y análisis de series temporales.',
    1
),
(
    'Máster en Inteligencia Artificial (M.Sc. in Artificial Intelligence)',
    'Universidad Politécnica de Valencia (UPV)',
    '2023-09-01',
    '2024-06-30',
    'Especialización en arquitecturas RAG, aprendizaje profundo, visión artificial y procesamiento de lenguaje natural.',
    1
);

-- ==========================================
-- 6. IDIOMAS
-- ==========================================
INSERT INTO idiomas (lengua, nivel, perfil_id)
VALUES 
    ('Español', 'Nativo', 1),
    ('Inglés', 'Profesional (B2/C1)', 1);

COMMIT;