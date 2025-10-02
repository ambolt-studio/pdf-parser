# 🔧 INSTRUCCIONES PARA ARREGLAR EL WORKFLOW MANUALMENTE

## ⚠️ PROBLEMA ACTUAL

El workflow tiene **22 nodos** pero solo **12 están conectados** correctamente. Necesitas conectar las 10 herramientas restantes manualmente en n8n.

---

## 🎯 SOLUCIÓN PASO A PASO

### Paso 1: Abre el Workflow en n8n

1. Ve a tu instancia de n8n
2. Busca el workflow **"Test-MCP-dev"** (ID: `FekDuQDY0dFCeH2u`)
3. Ábrelo en modo edición

---

### Paso 2: Conecta TODAS las Herramientas

Para **CADA UNA** de estas herramientas, haz lo siguiente:

#### Herramientas por Conectar:

1. **Create Issue**
2. **List Issues**
3. **Get Issue**
4. **Update Issue**
5. **Add Comment to Issue**
6. **Delete File**
7. **Get File Content**
8. **Get Release**
9. **List Releases**

#### Cómo Conectar Cada Herramienta:

1. **Busca el nodo** de la herramienta (ej: "Create Issue")
2. **Haz clic en el círculo de salida** del nodo (a la derecha)
   - Verás que dice **"ai_tool"**
3. **Arrastra una línea** hasta el nodo **"AI Agent - GitHub Manager"**
4. **Conecta al puerto de entrada** que dice **"ai_tool"**
5. **Repite** para las otras 9 herramientas

---

### Paso 3: Verifica las Conexiones

Una vez conectadas todas, deberías ver:

```
Trigger (When chat message received)
   └─► AI Agent - GitHub Manager
        ├─► OpenAI Chat Model (ai_languageModel)
        ├─► Simple Memory (ai_memory)
        └─► 19 GitHub Tools (ai_tool):
             ├─► CreateFile ✅
             ├─► listFile ✅
             ├─► getFile ✅
             ├─► editFile ✅
             ├─► getRepository ✅
             ├─► getPullRequest ✅
             ├─► approvePR ✅
             ├─► createRelease ✅
             ├─► Create a release in GitHub ✅
             ├─► Create Issue ⚠️ CONECTAR
             ├─► List Issues ⚠️ CONECTAR
             ├─► Get Issue ⚠️ CONECTAR
             ├─► Update Issue ⚠️ CONECTAR
             ├─► Add Comment to Issue ⚠️ CONECTAR
             ├─► Delete File ⚠️ CONECTAR
             ├─► Get File Content ⚠️ CONECTAR
             ├─► Get Release ⚠️ CONECTAR
             └─► List Releases ⚠️ CONECTAR
```

---

### Paso 4: Limpia Nodos Duplicados (Opcional)

Tienes algunos nodos duplicados que puedes eliminar:

- **"Create a release in GitHub"** - Duplicado de "createRelease"
- **"getFile"** - Está configurado como "edit" pero se llama "getFile"

Para eliminar:
1. Haz clic derecho en el nodo
2. Selecciona "Delete"

---

### Paso 5: Reorganiza Visualmente (Opcional pero Recomendado)

Para que el workflow sea más fácil de entender:

1. **Agrupa las herramientas por tipo**:
   ```
   [Archivos]     [Issues]      [PRs]        [Releases]    [Repo]
   ├ List         ├ Create      ├ List       ├ Create      └ Get Info
   ├ Get          ├ List        └ Review     ├ Get
   ├ Create       ├ Get                      └ List
   ├ Edit         ├ Edit
   └ Delete       └ Comment
   ```

2. **Posiciona el Agente en el centro**
3. **Coloca todas las herramientas alrededor** del agente
4. **Deja el Trigger a la izquierda**
5. **Coloca Model y Memory arriba/abajo del Agente**

---

## 📋 CHECKLIST DE VERIFICACIÓN

Antes de activar el workflow, verifica:

- [ ] El trigger "When chat message received" está conectado al agente
- [ ] "OpenAI Chat Model" está conectado al agente (ai_languageModel)
- [ ] "Simple Memory" está conectado al agente (ai_memory)
- [ ] Todas las 15+ herramientas GitHub están conectadas al agente (ai_tool)
- [ ] No hay nodos sueltos sin conexión
- [ ] El workflow se ve organizado y comprensible

---

## ✅ Resultado Final Esperado

Deberías tener:

- **1 Trigger**: When chat message received
- **1 Agente**: AI Agent - GitHub Manager
- **1 Modelo**: OpenAI Chat Model (GPT-4o-mini)
- **1 Memoria**: Simple Memory
- **15+ Herramientas GitHub**: Todas conectadas al agente

**Total**: ~20 nodos, todos conectados correctamente

---

## 🚀 Activar y Probar

Una vez todo esté conectado:

1. **Guarda el workflow** (Ctrl+S o botón Save)
2. **Activa el workflow** (toggle "Active")
3. **Abre el chat** (click en "When chat message received" → "Open chat")
4. **Prueba**:
   ```
   "Hola, ¿qué puedes hacer?"
   "Lista los archivos del repositorio"
   "Crea un issue de prueba"
   "Muéstrame los PRs abiertos"
   ```

---

## 🎨 Visualización del Workflow Ideal

```
┌─────────────────────┐
│  Chat Trigger       │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│   AI Agent          │◄────── OpenAI Model
│   (Centro)          │
│                     │◄────── Memory
└──────────┬──────────┘
           │
           ├─────► [5 File Tools]
           ├─────► [5 Issue Tools]
           ├─────► [2 PR Tools]
           ├─────► [3 Release Tools]
           └─────► [1 Repo Tool]
```

---

## 💡 Tip Final

Si el workflow sigue siendo confuso:

1. **Exporta el workflow actual** (backup)
2. **Crea un workflow nuevo desde cero**
3. **Añade los nodos en este orden**:
   - Trigger
   - Agente
   - Modelo
   - Memoria
   - Luego las herramientas una por una
4. **Conéctalos inmediatamente** después de añadir cada uno

---

**Tiempo estimado**: 5-10 minutos
**Dificultad**: Fácil (solo arrastrar y soltar)

¡Cualquier duda, pregúntame!