<script setup>
import {
  ArrowDown,
  ArrowRight,
  Delete,
  Document,
  Finished,
  FolderOpened,
  Picture,
  Loading,
  Lock,
  Plus,
  Refresh,
  SwitchButton,
  View,
} from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import MarkdownIt from 'markdown-it'
import { computed, nextTick, onMounted, onUnmounted, ref } from 'vue'
import {
  createIncrementalTask,
  createTask,
  deleteCreativePoint,
  deleteTask,
  fetchCurrentUser,
  fetchReport,
  fetchTask,
  fetchTasks,
  generateCreativePointImage,
  generateCreativePointImagePrompt,
  login,
  logout,
  openTaskEvents,
} from './api/client'

const markdown = new MarkdownIt({
  html: false,
  linkify: true,
  breaks: true,
})

const source = ref('')
const analysisDepth = ref('standard')
const tasks = ref([])
const activeTaskId = ref(null)
const activeTask = ref(null)
const report = ref(null)
const loading = ref(false)
const reportLoading = ref(false)
const incrementalLoading = ref(false)
const eventSource = ref(null)
const reportPanel = ref(null)
const nowTick = ref(Date.now())
const durationBase = ref({})
const expandedScanGroups = ref({})
const imagePromptLoadingIds = ref({})
const imageGeneratingIds = ref({})
const imagePromptDialog = ref({
  visible: false,
  pointId: null,
  title: '',
  prompt: '',
})
const authChecked = ref(false)
const currentUser = ref(null)
const loginLoading = ref(false)
const loginForm = ref({
  username: 'admin',
  password: '',
})
let timer = null

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
  const doneCount = steps.filter((item) => ['completed', 'skipped', 'failed'].includes(item.status)).length
  return Math.round((doneCount / steps.length) * 100)
})

const scanGroups = computed(() => {
  const steps = activeTask.value?.steps || []
  const groups = []
  const groupMap = new Map()

  steps.forEach((step, index) => {
    const meta = parseStepRound(step.name)
    if (!groupMap.has(meta.key)) {
      const group = {
        key: meta.key,
        label: meta.label,
        order: meta.order,
        steps: [],
      }
      groupMap.set(meta.key, group)
      groups.push(group)
    }
    groupMap.get(meta.key).steps.push({
      ...step,
      display_name: meta.stepName || step.name,
      sourceIndex: index,
    })
  })

  groups.sort((left, right) => left.order - right.order)
  return groups.map((group, index) => {
    const doneCount = group.steps.filter((item) => ['completed', 'skipped'].includes(item.status)).length
    const failedCount = group.steps.filter((item) => item.status === 'failed').length
    const runningCount = group.steps.filter((item) => item.status === 'running').length
    const candidatesCount = group.steps.reduce((sum, item) => sum + Number(item.candidates_count || 0), 0)
    const filesCount = new Set(group.steps.flatMap((item) => item.files_scanned || [])).size
    let status = 'pending'
    if (failedCount) {
      status = 'failed'
    } else if (runningCount) {
      status = 'running'
    } else if (doneCount === group.steps.length) {
      status = 'completed'
    }

    return {
      ...group,
      doneCount,
      candidatesCount,
      filesCount,
      status,
      isLatest: index === groups.length - 1,
    }
  })
})

const runningStepName = computed(() => {
  const steps = activeTask.value?.steps || []
  const runningStep = [...steps].reverse().find((item) => item.status === 'running')
  return runningStep?.name || activeTask.value?.task.current_step || '准备项目'
})

const renderedReport = computed(() => markdown.render(report.value?.markdown || ''))

const activeDurationText = computed(() => formatTaskDuration(activeTask.value?.task))

onMounted(async () => {
  timer = window.setInterval(() => {
    nowTick.value = Date.now()
  }, 1000)
  await checkLogin()
})

onUnmounted(() => {
  if (timer) {
    window.clearInterval(timer)
  }
  eventSource.value?.close()
})

async function checkLogin() {
  try {
    currentUser.value = await fetchCurrentUser()
    await loadTasks()
  } catch {
    currentUser.value = null
  } finally {
    authChecked.value = true
  }
}

async function submitLogin() {
  if (!loginForm.value.username.trim() || !loginForm.value.password) {
    ElMessage.warning('请输入账号和密码')
    return
  }

  loginLoading.value = true
  try {
    currentUser.value = await login({
      username: loginForm.value.username.trim(),
      password: loginForm.value.password,
    })
    loginForm.value.password = ''
    await loadTasks()
    ElMessage.success('登录成功')
  } catch (error) {
    ElMessage.error(error.message || '登录失败')
  } finally {
    loginLoading.value = false
  }
}

async function submitLogout() {
  try {
    await logout()
  } finally {
    currentUser.value = null
    activeTaskId.value = null
    activeTask.value = null
    report.value = null
    tasks.value = []
    eventSource.value?.close()
    eventSource.value = null
  }
}

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
  rememberDurationBase(tasks.value)
}

async function openTask(taskId) {
  activeTaskId.value = taskId
  report.value = null
  activeTask.value = await fetchTask(taskId)
  rememberDurationBase([activeTask.value.task])
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
    rememberDurationBase([activeTask.value.task])
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

async function viewReport() {
  if (!activeTask.value) return

  reportLoading.value = true
  try {
    await loadReport(activeTask.value.task.id)
    if (!report.value) {
      ElMessage.warning('当前任务还没有生成报告')
      return
    }
    await nextTick()
    reportPanel.value?.scrollIntoView({ behavior: 'smooth', block: 'start' })
    ElMessage.success('已定位到最终报告')
  } finally {
    reportLoading.value = false
  }
}

async function startIncremental() {
  if (!activeTask.value || activeTask.value.task.status === 'running') return

  incrementalLoading.value = true
  try {
    await createIncrementalTask(activeTask.value.task.id, {
      analysis_depth: 'deep',
    })
    report.value = null
    await openTask(activeTask.value.task.id)
    ElMessage.success('增量识别已开始')
  } catch (error) {
    ElMessage.error(error.message || '增量识别启动失败')
  } finally {
    incrementalLoading.value = false
  }
}

async function removeTask(item) {
  try {
    await ElMessageBox.confirm(
      `确认删除「${item.project_name}」这条蒸馏记录吗？删除后报告、扫描步骤和创意点都会一起删除。`,
      '删除历史任务',
      {
        confirmButtonText: '删除',
        cancelButtonText: '取消',
        type: 'warning',
      },
    )
    await deleteTask(item.id)
    if (activeTaskId.value === item.id) {
      activeTaskId.value = null
      activeTask.value = null
      report.value = null
      eventSource.value?.close()
      eventSource.value = null
    }
    await loadTasks()
    ElMessage.success('历史任务已删除')
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error(error.message || '删除失败')
    }
  }
}

async function removeCreativePoint(point) {
  if (!activeTask.value) return
  try {
    await ElMessageBox.confirm(
      `确认删除「${point.title}」这个创意点吗？`,
      '删除创意点',
      {
        confirmButtonText: '删除',
        cancelButtonText: '取消',
        type: 'warning',
      },
    )
    await deleteCreativePoint(point.id)
    activeTask.value = await fetchTask(activeTask.value.task.id)
    await loadTasks()
    ElMessage.success('创意点已删除')
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error(error.message || '删除失败')
    }
  }
}

async function prepareImagePrompt(point) {
  if (!activeTask.value) return

  imagePromptLoadingIds.value = {
    ...imagePromptLoadingIds.value,
    [point.id]: true,
  }
  try {
    const data = await generateCreativePointImagePrompt(point.id)
    activeTask.value = await fetchTask(activeTask.value.task.id)
    imagePromptDialog.value = {
      visible: true,
      pointId: point.id,
      title: point.title,
      prompt: data.prompt || '',
    }
  } catch (error) {
    ElMessage.error(error.message || '图片提示词生成失败')
  } finally {
    imagePromptLoadingIds.value = {
      ...imagePromptLoadingIds.value,
      [point.id]: false,
    }
  }
}

async function confirmGenerateImage() {
  if (!activeTask.value || !imagePromptDialog.value.pointId) return
  const prompt = imagePromptDialog.value.prompt.trim()
  if (prompt.length < 20) {
    ElMessage.warning('图片提示词太短，请补充后再生成')
    return
  }

  const pointId = imagePromptDialog.value.pointId
  imageGeneratingIds.value = {
    ...imageGeneratingIds.value,
    [pointId]: true,
  }
  try {
    await generateCreativePointImage(pointId, { prompt })
    activeTask.value = await fetchTask(activeTask.value.task.id)
    imagePromptDialog.value.visible = false
    ElMessage.success('释义图已生成')
  } catch (error) {
    activeTask.value = await fetchTask(activeTask.value.task.id)
    ElMessage.error(error.message || '释义图生成失败')
  } finally {
    imageGeneratingIds.value = {
      ...imageGeneratingIds.value,
      [pointId]: false,
    }
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
    'scan-item-failed': step.status === 'failed',
    'scan-item-skipped': step.status === 'skipped',
  }
}

function parseStepRound(name) {
  const normalizedName = String(name || '')
  const incrementalMatch = normalizedName.match(/^第(\d+)轮增量\s*[·.]\s*(.+)$/)
  if (incrementalMatch) {
    const round = Number(incrementalMatch[1])
    return {
      key: `round-${round}`,
      label: `第 ${round} 轮增量`,
      order: round,
      stepName: incrementalMatch[2],
    }
  }
  return {
    key: 'round-1',
    label: '初始识别',
    order: 1,
    stepName: normalizedName,
  }
}

function isScanGroupExpanded(group) {
  const isActiveRunning = activeTask.value?.task.status === 'running'
  return expandedScanGroups.value[group.key] ?? (group.isLatest && isActiveRunning)
}

function toggleScanGroup(group) {
  expandedScanGroups.value = {
    ...expandedScanGroups.value,
    [group.key]: !isScanGroupExpanded(group),
  }
}

function formatTaskDuration(task) {
  if (!task) return ''
  if (Number.isFinite(task.duration_seconds)) {
    return formatSeconds(currentDurationSeconds(task))
  }

  const startValue = task.started_at || task.created_at
  if (!startValue) return ''

  const startTime = parseTime(startValue)
  const endTime = task.finished_at ? parseTime(task.finished_at) : nowTick.value
  if (!startTime || !endTime || endTime < startTime) return ''

  const seconds = Math.max(0, Math.floor((endTime - startTime) / 1000))
  return formatSeconds(seconds)
}

function rememberDurationBase(taskItems) {
  taskItems.forEach((task) => {
    if (!task || !Number.isFinite(task.duration_seconds)) return
    durationBase.value[task.id] = {
      seconds: task.duration_seconds,
      capturedAt: Date.now(),
      status: task.status,
    }
  })
}

function currentDurationSeconds(task) {
  const base = durationBase.value[task.id]
  if (!base || task.status !== 'running') {
    return task.duration_seconds
  }
  return base.seconds + Math.floor((nowTick.value - base.capturedAt) / 1000)
}

function formatPlainExplanation(value) {
  return String(value || '')
    .replace(/^大白话讲[，,：:]?\s*/, '')
    .replace(/^大白话[，,：:]?\s*/, '')
}

function parseTime(value) {
  const normalized = /(?:Z|[+-]\d{2}:\d{2})$/.test(value) ? value : `${value}Z`
  const time = Date.parse(normalized)
  return Number.isNaN(time) ? 0 : time
}

function formatSeconds(totalSeconds) {
  const hours = Math.floor(totalSeconds / 3600)
  const minutes = Math.floor((totalSeconds % 3600) / 60)
  const seconds = totalSeconds % 60
  if (hours > 0) {
    return `${hours}小时${minutes}分${seconds}秒`
  }
  if (minutes > 0) {
    return `${minutes}分${seconds}秒`
  }
  return `${seconds}秒`
}
</script>

<template>
  <div v-if="authChecked && !currentUser" class="login-page">
    <section class="login-panel">
      <div class="brand login-brand">
        <div class="brand-mark">蒸</div>
        <div>
          <h1>Git 创意蒸馏器</h1>
          <p>请先登录后使用工作台</p>
        </div>
      </div>
      <el-form class="login-form" @submit.prevent="submitLogin">
        <el-form-item>
          <el-input
            v-model="loginForm.username"
            size="large"
            placeholder="账号"
            :prefix-icon="Lock"
            @keyup.enter="submitLogin"
          />
        </el-form-item>
        <el-form-item>
          <el-input
            v-model="loginForm.password"
            size="large"
            type="password"
            show-password
            placeholder="密码"
            :prefix-icon="Lock"
            @keyup.enter="submitLogin"
          />
        </el-form-item>
        <el-button type="primary" size="large" :loading="loginLoading" @click="submitLogin">
          登录
        </el-button>
      </el-form>
    </section>
  </div>

  <div v-else-if="!authChecked" class="login-page">
    <el-icon class="spin-icon loading-mark"><Loading /></el-icon>
  </div>

  <div v-else class="app-shell">
    <aside class="sidebar">
      <div class="brand">
        <div class="brand-mark">蒸</div>
        <div>
          <h1>Git 创意蒸馏器</h1>
          <p>🦊狐狸哥哥工作台</p>
        </div>
      </div>

      <div class="history-head">
        <span>历史任务</span>
        <div class="sidebar-actions">
          <el-button :icon="Refresh" circle size="small" title="刷新任务" @click="loadTasks" />
          <el-button :icon="SwitchButton" circle size="small" title="退出登录" @click="submitLogout" />
        </div>
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
          <span v-if="formatTaskDuration(item)" class="task-duration">
            {{ item.status === 'running' ? '已运行' : '耗时' }} {{ formatTaskDuration(item) }}
          </span>
          <el-button
            class="task-delete"
            :icon="Delete"
            circle
            size="small"
            title="删除历史任务"
            @click.stop="removeTask(item)"
          />
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
            <span v-if="activeDurationText" class="duration-pill">
              {{ activeTask.task.status === 'running' ? '已运行' : '耗时' }} {{ activeDurationText }}
            </span>
            <el-button
              :icon="Plus"
              :loading="incrementalLoading"
              :disabled="activeTask.task.status === 'running' || activeTask.task.status === 'pending'"
              @click="startIncremental"
            >
              增量识别
            </el-button>
            <el-button :icon="View" :loading="reportLoading" @click="viewReport">查看报告</el-button>
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
                <p>
                  已运行 {{ activeDurationText || '0秒' }}，仓库读取和 Claude Code 分析可能需要几十秒到几分钟，请稍等。
                </p>
              </div>
            </div>
            <div v-if="activeTask.task.status === 'failed'" class="failed-banner">
              <strong>分析失败</strong>
              <p>{{ activeTask.task.error_message || '任务执行失败，但没有返回具体错误。' }}</p>
            </div>
            <el-progress
              v-if="activeTask.steps.length"
              :percentage="scanProgress"
              :indeterminate="activeTask.task.status === 'running'"
              :duration="2"
              class="scan-progress"
            />
            <div class="scan-round-list">
              <section v-for="group in scanGroups" :key="group.key" class="scan-round">
                <button class="scan-round-head" type="button" @click="toggleScanGroup(group)">
                  <span class="scan-round-title">
                    <el-icon>
                      <ArrowDown v-if="isScanGroupExpanded(group)" />
                      <ArrowRight v-else />
                    </el-icon>
                    <strong>{{ group.label }}</strong>
                  </span>
                  <span class="scan-round-meta">
                    <span>{{ group.doneCount }}/{{ group.steps.length }}</span>
                    <span>候选 {{ group.candidatesCount }} 个</span>
                    <span>文件 {{ group.filesCount }} 个</span>
                    <el-tag :type="tagType(group.status)" size="small">
                      <el-icon v-if="group.status === 'running'" class="spin-icon"><Loading /></el-icon>
                      {{ statusText[group.status] || group.status }}
                    </el-tag>
                  </span>
                </button>
                <div v-show="isScanGroupExpanded(group)" class="scan-list">
                  <div v-for="step in group.steps" :key="step.id" :class="scanItemClass(step)">
                    <div class="scan-title">
                      <strong>{{ step.display_name }}</strong>
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
              </section>
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
                <div>
                  <h3>{{ point.title }}</h3>
                  <span v-if="point.source_round > 1" class="round-label">第 {{ point.source_round }} 轮发现</span>
                </div>
                <div class="creative-actions">
                  <el-tag type="success">{{ point.score.toFixed(1) }}</el-tag>
                  <el-button
                    :icon="Picture"
                    size="small"
                    :loading="imagePromptLoadingIds[point.id]"
                    :disabled="activeTask.task.status === 'running' || activeTask.task.status === 'pending'"
                    @click="prepareImagePrompt(point)"
                  >
                    {{ point.image_prompt ? '调整图片提示词' : '生成图片提示词' }}
                  </el-button>
                  <el-button
                    :icon="Delete"
                    circle
                    size="small"
                    title="删除创意点"
                    :disabled="activeTask.task.status === 'running' || activeTask.task.status === 'pending'"
                    @click="removeCreativePoint(point)"
                  />
                </div>
              </div>
              <div class="creative-tags">
                <el-tag>{{ point.innovation_type }}</el-tag>
                <el-tag type="info">{{ point.innovation_layer }}</el-tag>
              </div>
              <div v-if="point.image_url || point.image_status === 'failed'" class="creative-image-box">
                <img v-if="point.image_url" :src="point.image_url" :alt="`${point.title} 释义图`" />
                <div v-if="point.image_status === 'failed'" class="image-error">
                  {{ point.image_error || '释义图生成失败，请检查 MiniMax 配置后重试。' }}
                </div>
                <details v-if="point.image_prompt" class="image-prompt">
                  <summary>查看图片提示词</summary>
                  <p>{{ point.image_prompt }}</p>
                </details>
              </div>
              <div v-if="point.plain_explanation" class="plain-explanation">
                <strong>大白话：</strong>{{ formatPlainExplanation(point.plain_explanation) }}
              </div>
              <div v-if="point.application_scenarios?.length" class="application-scenarios">
                <strong>应用场景</strong>
                <div class="scenario-list">
                  <div v-for="scenario in point.application_scenarios" :key="scenario.name" class="scenario-item">
                    <span>{{ scenario.name }}</span>
                    <p>{{ scenario.description }}</p>
                  </div>
                </div>
              </div>
              <p v-if="point.discovery_reason" class="discovery-reason">
                <strong>增量发现原因：</strong>{{ point.discovery_reason }}
              </p>
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

        <section v-if="report" ref="reportPanel" class="panel report-panel">
          <div class="panel-title">
            <span>最终报告</span>
            <span>{{ report.created_at }}</span>
          </div>
          <div class="markdown-body" v-html="renderedReport"></div>
        </section>
      </template>
    </main>

    <el-dialog
      v-model="imagePromptDialog.visible"
      title="确认图片提示词"
      width="680px"
      class="image-prompt-dialog"
    >
      <p class="dialog-tip">
        先检查这段 Prompt 是否准确表达创意点价值，可以直接修改；确认后才会调用 MiniMax 生成图片。
      </p>
      <el-input
        v-model="imagePromptDialog.prompt"
        type="textarea"
        :rows="10"
        maxlength="3000"
        show-word-limit
      />
      <template #footer>
        <el-button @click="imagePromptDialog.visible = false">取消</el-button>
        <el-button
          type="primary"
          :loading="imageGeneratingIds[imagePromptDialog.pointId]"
          @click="confirmGenerateImage"
        >
          确认生成图片
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>
