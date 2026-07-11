// app.js
App({
  onLaunch() {
    // 首次启动: 展示免责说明
    const seen = wx.getStorageSync('disclaimer_seen')
    if (!seen) {
      wx.showModal({
        title: '免责声明',
        content: '本设备是家庭健康风险提示工具, 不是医疗诊断设备。如出现面部歪斜/言语不清/单侧肢体无力等症状, 请立即拨打 120 (脑卒中黄金时间窗 4.5 小时)。',
        showCancel: false,
        confirmText: '我已知悉',
        success: () => wx.setStorageSync('disclaimer_seen', 1)
      })
    }
  },
  globalData: {
    // 后端 HTTP 基址; VPS 无域名/无 TLS 时, 微信小程序需要用 IP + HTTPS + 备案, 或改用开发者工具的"不校验合法域名"
    apiBase: 'http://106.75.229.61:8000',
    deviceId: 'sg-0001'
  }
})
