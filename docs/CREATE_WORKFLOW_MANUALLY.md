# 🚀 IMPORTAR WORKFLOW LIMPIO - Instrucciones

## ⚠️ IMPORTANTE

La API de n8n tiene limitaciones para crear workflows programáticamente con conexiones `ai_tool`. 

**La mejor solución es que COPIES el workflow JSON y lo importes manualmente en n8n.**

---

## 📋 PASO A PASO

### Opción 1: Importar desde Template (RECOMENDADO ⭐)

1. **Ve a n8n Templates**: https://n8n.io/workflows/?search=AI+agent+chat
2. **Busca** un template de "AI Agent Chat" similar
3. **Importa el template** a tu n8n
4. **Modifica** cambiando las herramientas por las de GitHub
5. **Conecta** todas las herramientas al agente

**Esto te ahorrará tiempo** porque el template ya tiene la estructura correcta de conexiones.

---

### Opción 2: Crear Manualmente (Paso a Paso)

#### 1. Crea un Workflow Nuevo

En n8n:
- Click en "**+ New workflow**"
- Nombre: "**GitHub Agent - pdf-parser**"

#### 2. Agrega los Nodos Base (en este orden)

1. **Chat Trigger**:
   - Busca: "When chat message received"
   - Posición: Izquierda central

2. **AI Agent**:
   - Busca: "AI Agent"
   - Posición: Centro
   - System Message:
   ```
   Eres un asistente para gestionar el repositorio GitHub 'pdf-parser' de ambolt-studio.

   CAPACIDADES:
   📁 Archivos: listar, obtener, crear, editar, eliminar
   🎯 Issues: crear, listar, obtener, editar, comentar  
   🔄 Pull Requests: listar, crear reviews
   📊 Releases: crear, obtener, listar
   📦 Repositorio: obtener información

   Responde en español. Confirma acciones destructivas.
   ```

3. **OpenAI Model**:
   - Busca: "OpenAI Chat Model"
   - Modelo: **gpt-4o-mini**
   - Posición: Arriba derecha del agente

4. **Memory**:
   - Busca: "Window Buffer Memory"
   - Posición: Abajo derecha del agente

#### 3. Conecta los Nodos Base

```
Chat Trigger ──[main]──► AI Agent
                         ▲
                         ├──[ai_languageModel]── OpenAI Model
                         └──[ai_memory]────────── Memory
```

**Cómo conectar**:
- Chat Trigger: Arrastra desde el círculo derecho → AI Agent (puerto "main")
- OpenAI Model: Arrastra desde el círculo derecho → AI Agent (puerto "ai_languageModel")
- Memory: Arrastra desde el círculo derecho → AI Agent (puerto "ai_memory")

#### 4. Agrega las Herramientas GitHub

**Para CADA herramienta** de la lista abajo:
1. Busca "**GitHub Tool**"
2. Configura según la tabla
3. Arrastra desde **ai_tool** (derecha) → **AI Agent** (puerto "ai_tool")

**Configuración de cada herramienta**:

| Nombre | Resource | Operation | Parámetros AI |
|--------|----------|-----------|---------------|
| **List Files** | file | list | File_Path |
| **Get File** | file | get | File_Path |
| **Create File** | file | create | File_Path, File_Content, Commit_Message |
| **Edit File** | file | edit | File_Path, File_Content, Commit_Message |
| **Delete File** | file | delete | File_Path, Commit_Message |
| **Create Issue** | issue | create | Issue_Title, Issue_Body |
| **List Issues** | repository | getIssues | - |
| **Get Issue** | issue | get | Issue_Number |
| **Edit Issue** | issue | edit | Issue_Number |
| **Comment on Issue** | issue | createComment | Issue_Number, Comment_Body |
| **List PRs** | repository | getPullRequests | - |
| **Review PR** | review | create | PR_Number |
| **Create Release** | release | create | Tag |
| **Get Release** | release | get | Release_ID |
| **List Releases** | release | getMany | - |
| **Get Repository Info** | repository | get | - |

**Configuración común para TODAS**:
- Owner: `ambolt-studio`
- Repository: `pdf-parser`
- Credential: Tu credencial de GitHub

**Para los parámetros AI**, usa esta sintaxis:
```
={{ $fromAI('Nombre_Parametro', 'valor_default', 'tipo') }}
```

#### 5. Organiza Visualmente

Agrupa las herramientas:
```
[Fila 1 - Archivos]     
List Files → Get File → Create File → Edit File → Delete File

[Fila 2 - Issues]
Create Issue → List Issues → Get Issue → Edit Issue → Comment

[Fila 3 - PRs y Releases]
List PRs → Review PR → Create Release → Get Release → List Releases

[Fila 4 - Centro]
             Chat ──► Agent ◄── Model
                        ▲         Memory
                        │
                   Get Repo Info
```

#### 6. Verifica Conexiones

Deberías ver en el AI Agent:
- ✅ 1 conexión **main** (desde Chat Trigger)
- ✅ 1 conexión **ai_languageModel** (desde OpenAI Model)
- ✅ 1 conexión **ai_memory** (desde Memory)
- ✅ 16 conexiones **ai_tool** (desde todas las herramientas GitHub)

**Total**: 19 conexiones entrantes al AI Agent

#### 7. Guarda y Activa

1. **Ctrl+S** o botón "**Save**"
2. Click en "**Active**" (toggle arriba)
3. El workflow está listo ✅

---

## 🧪 Probar el Workflow

1. Click en "**When chat message received**"
2. Click en "**Open chat**" o "**Test workflow**"
3. Prueba con:

```
Hola, ¿qué puedes hacer?
```

```
Lista los archivos del repositorio
```

```
Crea un issue de prueba titulado "Test desde el agente"
```

```
Muéstrame los PRs abiertos
```

---

## 📊 Resultado Esperado

**Nodos totales**: 20
- 1 Chat Trigger
- 1 AI Agent  
- 1 OpenAI Model
- 1 Memory
- 16 GitHub Tools

**Conexiones totales**: 19 (todas hacia el AI Agent)

**Tiempo estimado**: 15-20 minutos

---

## 💡 Consejos

1. **Usa credenciales guardadas**: Configura las credenciales de GitHub y OpenAI una vez y reutilízalas
2. **Copia/pega parámetros**: Después de configurar una herramienta, puedes copiar los parámetros AI a otras similares
3. **Agrupa visualmente**: Un workflow organizado es más fácil de mantener
4. **Prueba incrementalmente**: Después de agregar 5 herramientas, prueba que funcionen antes de seguir
5. **Duplica nodos**: Si necesitas una herramienta similar, duplica (Ctrl+D) y modifica

---

## ❓ Preguntas Frecuentes

**P: ¿Por qué no usar la API para crear el workflow?**
R: La API de n8n tiene limitaciones con las conexiones `ai_tool`. Es más rápido hacerlo manualmente.

**P: ¿Puedo usar otro modelo de IA?**
R: Sí, puedes usar GPT-4o, Claude, etc. Solo cambia el nodo del modelo.

**P: ¿Funciona con otros repositorios?**
R: Sí, solo cambia el owner y repository en cada herramienta.

**P: ¿Cuánto cuesta ejecutar el workflow?**
R: Depende del uso. GPT-4o-mini es muy económico (~$0.15 por millón de tokens de entrada).

---

## 🎯 Siguiente Nivel

Una vez que funcione básico, puedes:

1. **Agregar más herramientas**: User operations, Organization, Workflows
2. **Mejorar el system message**: Agregar contexto específico de tu proyecto
3. **Agregar memoria persistente**: Usar Postgres en vez de Window Buffer
4. **Crear sub-workflows**: Para operaciones complejas
5. **Integrar con otros servicios**: Slack, Discord, Telegram

---

**¿Necesitas ayuda?** Pregúntame sobre cualquier paso específico.

## 📚 Referencias

- [n8n AI Agent Docs](https://docs.n8n.io/integrations/builtin/cluster-nodes/sub-nodes/n8n-nodes-langchain.agent/)
- [GitHub Tool Docs](https://docs.n8n.io/integrations/builtin/app-nodes/n8n-nodes-base.github/)
- [n8n Templates](https://n8n.io/workflows/)
