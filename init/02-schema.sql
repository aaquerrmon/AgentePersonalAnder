CREATE TABLE IF NOT EXISTS perfil (
    id SERIAL PRIMARY KEY,
    nombre_completo VARCHAR(150) NOT NULL,
    titular VARCHAR(255) NOT NULL,
    biografia TEXT,
    ubicacion VARCHAR(100),
    email VARCHAR(150),
    github_url VARCHAR(255),
    linkedin_url VARCHAR(255),
    web_personal VARCHAR(255)
);

CREATE TABLE IF NOT EXISTS experiencia (
    id SERIAL PRIMARY KEY,
    empresa VARCHAR(150) NOT NULL,
    rol VARCHAR(150) NOT NULL,
    tipo_contrato VARCHAR(50),
    fecha_inicio DATE NOT NULL,
    fecha_fin DATE,
    descripcion TEXT,
    perfil_id INT REFERENCES perfil(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS proyectos (
    id SERIAL PRIMARY KEY,
    titulo VARCHAR(150) NOT NULL,
    descripcion_completa TEXT,
    tipo VARCHAR(50),
    url_publica VARCHAR(255),
    destacado BOOLEAN DEFAULT FALSE,
    perfil_id INT REFERENCES perfil(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS tecnologias (
    id SERIAL PRIMARY KEY,
    nombre VARCHAR(100) NOT NULL UNIQUE,
    categoria VARCHAR(50), -- Ej: 'Backend', 'Machine Learning', 'DevOps'
    nivel VARCHAR(50), -- Ej: 'Avanzado', 'Intermedio'
    perfil_id INT REFERENCES perfil(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS idiomas (
    id SERIAL PRIMARY KEY,
    lengua VARCHAR(100) NOT NULL UNIQUE,
    nivel VARCHAR(50),
    perfil_id INT REFERENCES perfil(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS educacion (
    id SERIAL PRIMARY KEY,
    titulo VARCHAR(150) NOT NULL,
    institucion VARCHAR(150) NOT NULL,
    fecha_inicio DATE,
    fecha_fin DATE,
    detalles TEXT,
    perfil_id INT REFERENCES perfil(id) ON DELETE CASCADE
);


-- RAG (Retrieval-Augmented Generation) Tables

CREATE TABLE IF NOT EXISTS documentos_rag (
    id SERIAL PRIMARY KEY,
    titulo VARCHAR(255) NOT NULL,
    fuente VARCHAR(100), -- Ej: 'pdf_tfg', 'readme_github', 'experiencia_upv'
    proyecto_id INT REFERENCES proyectos(id) ON DELETE SET NULL, -- Opcional: vincula el doc a un proyecto
    perfil_id INT REFERENCES perfil(id) ON DELETE CASCADE,
    metadata JSONB DEFAULT '{}'::jsonb -- Ej: {"autor": "Ander", "año": 2026, "idioma": "es"}
);

CREATE TABLE IF NOT EXISTS chunks_rag (
    id SERIAL PRIMARY KEY,
    doc_id INT NOT NULL REFERENCES documentos_rag(id) ON DELETE CASCADE,
    chunk_index INT NOT NULL, -- Tu 'chunk_id' (0, 1, 2... indica el orden del fragmento en el documento)
    texto TEXT NOT NULL,      -- Tu 'text' (el contenido del fragmento)
    metadata JSONB DEFAULT '{}'::jsonb, -- Muy útil para guardar {"pagina": 12, "seccion": "Arquitectura"}
    embedding VECTOR(384),   -- intfloat/multilingual-e5-small 384
    UNIQUE (doc_id, chunk_index) -- Evita duplicar el mismo número de chunk para un mismo documento
);

-- 3. Índices para acelerar las búsquedas del RAG
-- Índice vectorial HNSW para búsqueda semántica ultrarrápida (Cosine Distance)
CREATE INDEX IF NOT EXISTS idx_chunks_embedding 
ON chunks_rag USING hnsw (embedding vector_cosine_ops);

-- Índice GIN sobre el JSONB por si quieres filtrar por metadatos antes de buscar vectores
CREATE INDEX IF NOT EXISTS idx_chunks_metadata 
ON chunks_rag USING gin (metadata);