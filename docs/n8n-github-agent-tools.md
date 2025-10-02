# GitHub Agent Tools para pdf-parser

## Resumen
Este documento describe todas las herramientas (tools) necesarias para que un agente de IA pueda gestionar completamente el repositorio `pdf-parser` en GitHub.

## Herramientas Implementadas

### 📁 Gestión de Archivos

1. **List Files** - Listar archivos/directorios
   - Parámetros: File_Path (string, opcional)
   - Uso: Explorar la estructura del repositorio

2. **Get File Content** - Obtener contenido de un archivo
   - Parámetros: File_Path (string, requerido)
   - Uso: Leer el contenido de archivos específicos

3. **Create File** - Crear nuevo archivo
   - Parámetros:
     - File_Path (string, requerido)
     - File_Content (string, requerido)
     - Commit_Message (string, requerido)
   - Uso: Añadir nuevos archivos al repositorio

4. **Edit File** - Editar archivo existente
   - Parámetros:
     - File_Path (string, requerido)
     - File_Content (string, requerido)
     - Commit_Message (string, requerido)
   - Uso: Modificar archivos existentes

5. **Delete File** - Eliminar archivo
   - Parámetros:
     - File_Path (string, requerido)
     - Commit_Message (string, requerido)
   - Uso: Remover archivos del repositorio

### 🎯 Gestión de Issues

6. **Create Issue** - Crear nuevo issue
   - Parámetros:
     - Issue_Title (string, requerido)
     - Issue_Body (string, requerido)
     - Labels (string, opcional)
   - Uso: Reportar bugs, solicitar features, documentar tareas

7. **List Issues** - Listar issues
   - Parámetros:
     - Return_All (boolean, default: false)
     - State (string, default: 'open') - valores: open, closed, all
   - Uso: Ver issues existentes

8. **Update Issue** - Actualizar issue
   - Parámetros:
     - Issue_Number (number, requerido)
     - New_Title (string, opcional)
     - New_Body (string, opcional)
     - State (string, opcional) - valores: open, closed
   - Uso: Modificar o cerrar issues

9. **Add Comment to Issue** - Comentar en issue
   - Parámetros:
     - Issue_Number (number, requerido)
     - Comment_Body (string, requerido)
   - Uso: Añadir seguimiento o información adicional

### 🔀 Gestión de Pull Requests

10. **Create Pull Request** - Crear PR
    - Parámetros:
      - PR_Title (string, requerido)
      - Head_Branch (string, requerido)
      - Base_Branch (string, default: 'main')
      - Description (string, requerido)
    - Uso: Proponer cambios para revisión

11. **List Pull Requests** - Listar PRs
    - Parámetros:
      - Return_All (boolean, default: false)
    - Uso: Ver PRs abiertos/cerrados

12. **Merge Pull Request** - Mergear PR
    - Parámetros:
      - PR_Number (number, requerido)
      - Merge_Method (string, default: 'merge') - valores: merge, squash, rebase
    - Uso: Integrar cambios aprobados

13. **Approve Pull Request** - Aprobar PR
    - Parámetros:
      - PR_Number (number, requerido)
    - Uso: Dar aprobación a cambios propuestos

### 🌿 Gestión de Branches

14. **Create Branch** - Crear rama
    - Parámetros:
      - Branch_Name (string, requerido)
      - From_Branch (string, default: 'main')
    - Uso: Crear ramas para desarrollo

15. **List Branches** - Listar ramas
    - Parámetros: Ninguno
    - Uso: Ver todas las ramas del repositorio

### 📊 Información y Releases

16. **List Commits** - Listar commits
    - Parámetros:
      - Return_All (boolean, default: false)
      - Branch_or_SHA (string, opcional)
    - Uso: Ver historial de cambios

17. **Get Repository Info** - Información del repo
    - Parámetros: Ninguno
    - Uso: Obtener estadísticas y metadata

18. **Create Release** - Crear release
    - Parámetros:
      - Tag (string, requerido)
      - Release_Name (string, opcional)
      - Release_Notes (string, opcional)
    - Uso: Publicar versiones

## Configuración del Agente

### System Message
```
Eres un asistente especializado en gestionar el repositorio GitHub 'pdf-parser' de ambolt-studio. 

Puedes:
- Listar, crear, editar y eliminar archivos
- Gestionar issues (crear, listar, actualizar, comentar)
- Gestionar pull requests (crear, listar, aprobar, mergear)
- Gestionar branches (crear, listar)
- Ver commits y releases
- Obtener información del repositorio

Siempre confirma acciones destructivas antes de ejecutarlas.
```

### Modelo Recomendado
- **GPT-4o-mini**: Balance entre costo y capacidad
- **GPT-4o**: Para tareas más complejas

### Memoria
- **Window Buffer Memory**: Mantiene contexto de la conversación

## Ejemplos de Uso

### Crear un feature
```
Usuario: "Crea una nueva rama feature/pdf-metadata y añade un archivo metadata_parser.py con una función básica"

Agente ejecutará:
1. Create Branch (Branch_Name: "feature/pdf-metadata")
2. Create File (File_Path: "metadata_parser.py", ...)
```

### Gestionar un bug
```
Usuario: "Lista los issues abiertos y crea uno nuevo para el bug del parser"

Agente ejecutará:
1. List Issues (State: "open")
2. Create Issue (Issue_Title: "Bug en parser", ...)
```

### Code Review
```
Usuario: "Muéstrame los PRs pendientes y aprueba el #5"

Agente ejecutará:
1. List Pull Requests
2. Approve Pull Request (PR_Number: 5)
```

## Seguridad

- ⚠️ **Acciones Destructivas**: El agente debe confirmar antes de:
  - Eliminar archivos
  - Mergear PRs
  - Cerrar issues
  - Crear releases

- 🔒 **Permisos**: El token de GitHub debe tener:
  - `repo` (acceso completo al repositorio)
  - `workflow` (si se gestionan GitHub Actions)

## Workflow JSON para n8n

Para implementar este agente en n8n, necesitarás:

1. **Chat Trigger**: Punto de entrada para interacción
2. **AI Agent**: Orquestador central
3. **OpenAI Model**: GPT-4o-mini o superior
4. **Memory**: Window Buffer Memory
5. **18 GitHub Tools**: Todas las herramientas listadas arriba

### Estructura de Conexiones
```
Chat Trigger → AI Agent
OpenAI Model → AI Agent (ai_languageModel)
Memory → AI Agent (ai_memory)
Todas las Tools → AI Agent (ai_tool)
```

## Instrucciones de Instalación

### Paso 1: Configurar Credenciales GitHub
1. Ve a GitHub Settings → Developer settings → Personal access tokens
2. Genera un token con scope `repo`
3. En n8n, añade las credenciales de GitHub API

### Paso 2: Configurar Credenciales OpenAI
1. Obtén tu API key de OpenAI
2. En n8n, añade las credenciales de OpenAI API

### Paso 3: Importar Workflow
1. Copia el workflow JSON (ver archivo adjunto)
2. En n8n, importa el workflow
3. Conecta las credenciales
4. Activa el workflow

### Paso 4: Probar el Agente
1. Abre el chat del workflow
2. Prueba comandos simples:
   - "Lista los archivos del repositorio"
   - "Muéstrame los issues abiertos"
   - "Crea una rama de prueba"

## Limitaciones Conocidas

- No puede ejecutar código localmente
- No puede clonar el repositorio completo
- Limitado por rate limits de GitHub API
- No puede gestionar GitHub Actions directamente
- No puede modificar settings del repositorio

## Mejoras Futuras

- [ ] Soporte para GitHub Projects
- [ ] Gestión de GitHub Actions
- [ ] Análisis de código con AI
- [ ] Generación automática de documentación
- [ ] Integración con CI/CD
- [ ] Notificaciones proactivas
- [ ] Métricas y reportes

## Troubleshooting

### El agente no puede crear archivos
- Verifica que el token tenga permisos `repo`
- Confirma que la rama existe
- Revisa que no haya protección de rama

### El agente no responde
- Verifica la conexión con OpenAI
- Revisa los límites de rate de la API
- Comprueba que el workflow esté activo

### Errores de autenticación
- Regenera el token de GitHub
- Verifica que las credenciales estén correctamente configuradas
- Asegúrate de que el token no haya expirado

## Soporte

Para problemas o sugerencias:
- GitHub Issues: https://github.com/ambolt-studio/pdf-parser/issues
- Documentación n8n: https://docs.n8n.io
- OpenAI API: https://platform.openai.com/docs
