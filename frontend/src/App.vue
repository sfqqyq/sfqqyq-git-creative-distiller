<script setup>
import { Document, Finished, FolderOpened, Loading, Refresh, View } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { computed, onMounted, ref } from 'vue'
import { createTask, fetchReport, fetchTask, fetchTasks, openTaskEvents } from './api/client'

const source = ref('')
const analysisDepth = ref('standard')
const tasks = ref([])
const activeTaskId = ref(null)
const activeTask = ref(null)
const report = ref(null)
const loading = ref(false)
const eventSource = ref(null)

const statusText = {
  pending: '等待中',
  running: '分析中',
  completed: '已完成',
  failed: '失败',
  skipped: '跳过',
}

const depthOptions = [
  { label: '快速', value: 'fast' },
  { label: '标准', value: 'standard' },
  { label: '深度', value: 'deep' },
]

const creativeTypeStats = computed(() => {
  const points = activeTask.value?.creative_points || []
  const stats = {}
  points.forEach((item) => {
    stats[item.innovation_type] = (stats[item.innovation_type] || 0) + 1
  })
  return Object.entries(stats).map(([name, count]) => ({ name, count }))
})

const scanProgress = computed(() => {
  const steps = activeTask.value?.steps || []
  if (!steps.length) return 0
  const doneCount = steps.filter((item) => ['completed', 'skipped'].includes(item.status)).length
  return Math.round((doneCount / steps.length) * 100)
})

const runningStepName = computed(() => {
  const steps = activeTask.value?.steps || []
  const runningStep = steps.find((item) => item.status === 'running')
  return runningStep?.name || activeTask.value?.task.current_step || '准备项目'
})

onMounted(async () => {
  await loadTasks()
})

async function submitTask() {
  if (!source.value.trim()) {
    ElMessage.warning('请输入 Git 仓库地址或本地项目路径')
    return
  }
  loading.value = true
  try {
    const data = await createTask({
      source: source.value.trim(),
      analysis_depth: analysisDepth.value,
    })
    source.value = ''
    await loadTasks()
    await openTask(data.task_id)
    ElMessage.success('分析任务已创建')
  } catch (error) {
    ElMessage.error(error.message)
  } finally {
    loading.value = false
  }
}

async function loadTasks() {
  tasks.value = await fetchTasks()
}

async function openTask(taskId) {
  activeTaskId.value = taskId
  report.value = null
  activeTask.value = await fetchTask(taskId)
  connectEvents(taskId)
  if (activeTask.value.task.status === 'completed') {
    await loadReport(taskId)
  }
}

function connectEvents(taskId) {
  if (eventSource.value) {
    eventSource.value.close()
  }
  eventSource.value = openTaskEvents(taskId)
  eventSource.value.onmessage = async () => {
    activeTask.value = await fetchTask(taskId)
    await loadTasks()
    if (activeTask.value.task.status === 'completed') {
      eventSource.value.close()
      await loadReport(taskId)
    }
    if (activeTask.value.task.status === 'failed') {
      eventSource.value.close()
    }
  }
}

async function loadReport(taskId) {
  try {
    report.value = await fetchReport(taskId)
  } catch {
    report.value = null
  }
}

function tagType(status) {
  if (status === 'completed') return 'success'
  if (status === 'running') return 'warning'
  if (status === 'failed') return 'danger'
  if (status === 'skipped') return 'info'
  return ''
}

function scanItemClass(step) {
  return {
    'scan-item': true,
    'scan-item-running': step.status === 'running',
    'scan-item-done': step.status === 'completed',
    'scan-item-skipped': step.status === 'skipped',
  }
}
</script>

<template>
  <div class="app-shell">
    <aside class="sidebar">
      <div class="brand">
        <div class="brand-mark">蒸</div>
        <div>
          <h1>Git 创意蒸馏器</h1>
          <p>源码创新点分析工作台</p>
        </div>
      </div>

      <div class="history-head">
        <span>历史任务</span>
        <el-button :icon="Refresh" circle size="small" @click="loadTasks" />
      </div>

      <div class="task-list">
        <button
          v-for="item in tasks"
          :key="item.id"
          class="task-item"
          :class="{ active: activeTaskId === item.id }"
          @click="openTask(item.id)"
        >
          <span class="task-name">{{ item.project_name }}</span>
          <span class="task-meta">
            <el-icon v-if="item.status === 'running'" class="spin-icon"><Loading /></el-icon>
            {{ statusText[item.status] || item.status }} · {{ item.creative_count }} 个创意
          </span>
        </button>
      </div>
    </aside>

    <main class="workspace">
      <section class="submit-panel">
        <div>
          <h2>新建项目蒸馏</h2>
          <p>输入 Git 仓库地址或服务器上的本地项目路径，系统会按 6 条扫描线发现创意点。</p>
        </div>
        <div class="submit-row">
          <el-input
            v-model="source"
            size="large"
            placeholder="例如 git@github.com:owner/repo.git 或 /home/project"
            clearable
            @keyup.enter="submitTask"
          />
          <el-segmented v-model="analysisDepth" :options="depthOptions" />
          <el-button type="primary" size="large" :loading="loading" @click="submitTask">开始蒸馏</el-button>
        </div>
      </section>

      <section v-if="!activeTask" class="empty-state">
        <el-icon><FolderOpened /></el-icon>
        <h3>还没有打开任务</h3>
        <p>创建一个分析任务，或从左侧历史任务中选择一个已有任务。</p>
      </section>

      <template v-else>
        <section class="task-summary">
          <div>
            <h2>{{ activeTask.project.name }}</h2>
            <p>{{ activeTask.project.source }}</p>
          </div>
          <div class="summary-actions">
            <el-tag :type="tagType(activeTask.task.status)" size="large" class="status-tag">
              <el-icon v-if="activeTask.task.status === 'running'" class="spin-icon"><Loading /></el-icon>
              {{ statusText[activeTask.task.status] || activeTask.task.status }}
            </el-tag>
            <el-button :icon="View" @click="loadReport(activeTask.task.id)">查看报告</el-button>
          </div>
        </section>

        <section class="content-grid">
          <div class="panel">
            <div class="panel-title">
              <el-icon><Finished /></el-icon>
              <span>扫描线进度</span>
            </div>
            <div v-if="activeTask.task.status === 'running'" class="running-banner">
              <el-icon class="spin-icon"><Loading /></el-icon>
              <div>
                <strong>正在处理：{{ runningStepName }}</strong>
                <p>仓库读取和 Claude Code 分析可能需要几十秒到几分钟，请稍等。</p>
              </div>
            </div>
            <el-progress
              v-if="activeTask.steps.length"
              :percentage="scanProgress"
              :indeterminate="activeTask.task.status === 'running'"
              :duration="2"
              class="scan-progress"
            />
            <div class="scan-list">
              <div v-for="step in activeTask.steps" :key="step.id" :class="scanItemClass(step)">
                <div class="scan-title">
                  <strong>{{ step.name }}</strong>
                  <el-tag :type="tagType(step.status)" size="small">
                    <el-icon v-if="step.status === 'running'" class="spin-icon"><Loading /></el-icon>
                    {{ statusText[step.status] || step.status }}
                  </el-tag>
                </div>
                <p>{{ step.message || '等待执行' }}</p>
                <div class="scan-foot">
                  <span>候选 {{ step.candidates_count }} 个</span>
                  <span>{{ step.files_scanned.join('，') || '暂无文件' }}</span>
                </div>
              </div>
            </div>
          </div>

          <div class="panel">
            <div class="panel-title">
              <el-icon><Document /></el-icon>
              <span>创意雷达</span>
            </div>
            <div class="radar">
              <div v-if="activeTask.task.status === 'running'" class="radar-waiting">
                <el-icon class="spin-icon"><Loading /></el-icon>
                <strong>正在等待创意点生成</strong>
                <p>扫描线完成后，这里会显示创意类型分布。</p>
              </div>
              <div v-for="item in creativeTypeStats" :key="item.name" class="radar-item">
                <span>{{ item.name }}</span>
                <strong>{{ item.count }}</strong>
              </div>
              <p v-if="creativeTypeStats.length === 0">任务完成后会在这里展示创意类型分布。</p>
            </div>
          </div>
        </section>

        <section class="panel">
          <div class="panel-title">
            <span>创意点</span>
            <span>{{ activeTask.creative_points.length }} 个</span>
          </div>
          <div class="creative-list">
            <article v-for="point in activeTask.creative_points" :key="point.id" class="creative-card">
              <div class="creative-head">
                <h3>{{ point.title }}</h3>
                <el-tag type="success">{{ point.score.toFixed(1) }}</el-tag>
              </div>
              <div class="creative-tags">
                <el-tag>{{ point.innovation_type }}</el-tag>
                <el-tag type="info">{{ point.innovation_layer }}</el-tag>
              </div>
              <p><strong>传统做法：</strong>{{ point.traditional_approach }}</p>
              <p><strong>创新做法：</strong>{{ point.new_approach }}</p>
              <p>{{ point.description }}</p>
              <div class="evidence">
                <strong>源码证据</strong>
                <span v-for="item in point.evidence" :key="`${item.file}-${item.line_start}`">
                  {{ item.file }}:{{ item.line_start }}-{{ item.line_end }}
                </span>
              </div>
            </article>
          </div>
        </section>

        <section v-if="report" class="panel report-panel">
          <div class="panel-title">
            <span>最终报告</span>
            <span>{{ report.created_at }}</span>
          </div>
          <pre>{{ report.markdown }}</pre>
        </section>
      </template>
    </main>
  </div>
</template>
