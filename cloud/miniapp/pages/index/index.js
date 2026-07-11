// pages/index/index.js
const app = getApp()

const LEVEL_ZH = {
  normal: '正常',
  warning: '警告',
  danger: '危险 · 请立即拨打 120',
  insufficient: '数据不足'
}

Page({
  data: {
    deviceId: '',
    level: 'insufficient',
    levelZh: '等待数据',
    final: '--',
    scores: { face:'--', speech:'--', tongue:'--', eye:'--', csi:'--' },
    advice: '暂无 AI 建议',
    adviceTs: '',
    adviceSource: '',
    lastTs: '',
    loading: false,
    error: ''
  },

  onLoad() {
    this.setData({ deviceId: app.globalData.deviceId })
    this.refresh()
    // 每 8s 自动拉一次
    this.timer = setInterval(() => this.refresh(), 8000)
  },

  onUnload() {
    if (this.timer) clearInterval(this.timer)
  },

  refresh() {
    const url = `${app.globalData.apiBase}/devices/${this.data.deviceId}/latest`
    this.setData({ loading: true, error: '' })
    wx.request({
      url,
      method: 'GET',
      timeout: 8000,
      success: (res) => {
        if (res.statusCode !== 200) {
          this.setData({ error: `HTTP ${res.statusCode}` })
          return
        }
        const d = res.data || {}
        const s = d.latest_scores || {}
        const adv = d.last_advice || {}
        this.setData({
          level: d.latest_level || 'insufficient',
          levelZh: LEVEL_ZH[d.latest_level] || '等待数据',
          final: s.final != null ? s.final : '--',
          scores: {
            face:   s.face   != null ? s.face   : '--',
            speech: s.speech != null ? s.speech : '--',
            tongue: s.tongue != null ? s.tongue : '--',
            eye:    s.eye    != null ? s.eye    : '--',
            csi:    s.csi    != null ? s.csi    : '--',
          },
          advice: adv.advice_text || '暂无 AI 建议',
          adviceTs: adv.ts ? new Date(adv.ts * 1000).toLocaleTimeString() : '',
          adviceSource: adv.source || '',
          lastTs: d.last_uplink_ts ? new Date(d.last_uplink_ts * 1000).toLocaleTimeString() : ''
        })
      },
      fail: (err) => {
        this.setData({ error: err.errMsg || 'network error' })
      },
      complete: () => this.setData({ loading: false })
    })
  },

  onCall120() {
    wx.makePhoneCall({ phoneNumber: '120' })
  }
})
