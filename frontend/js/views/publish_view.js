window.SB_VIEWS = window.SB_VIEWS || {};
window.SB_VIEWS["publish-view"] = {
  template: `
  <div class="two-col">
    <div>
      <div class="panel">
        <h2>发布上屏</h2>
        <p class="lead">甲：正式事务直写；乙：影子草案再升正。两边不得混用。</p>
        <p class="lead" style="color:var(--danger)">
          风险≥4 分区（如室外立柱屏）正式上屏必须同票填场控单号，缺号整笔拒写、正式发布零增。
        </p>
        <div class="row-form">
          <input v-model.number="form.screen_id" type="number" placeholder="屏幕ID" />
          <input v-model.number="form.playlist_id" type="number" placeholder="清单ID" />
          <input v-model.number="form.window_id" type="number" placeholder="时段ID" />
          <input v-model="form.summary" placeholder="摘要" />
        </div>
        <div class="row-form">
          <input v-model="form.field_ticket_no" placeholder="场控单号（风险≥4 必填）" style="min-width:220px" />
          <button class="primary" @click="official">正式发布（甲）</button>
          <button class="ghost" @click="shadow">写影子草案（乙）</button>
        </div>
        <div class="row-form">
          <input v-model.number="shadowId" type="number" placeholder="影子ID" />
          <input v-model="shadowTicket" placeholder="补场控单号" />
          <button class="ghost" @click="supplement">影子补票</button>
          <button class="primary" @click="promote">升正影子</button>
        </div>
        <p class="err" v-if="error">{{ error }}</p>
        <p v-if="msg">{{ msg }}</p>
      </div>
      <div class="panel">
        <h3>正式发布</h3>
        <table>
          <thead><tr><th>ID</th><th>屏幕</th><th>清单</th><th>时段</th><th>版本</th><th>场控单号</th><th>摘要</th></tr></thead>
          <tbody>
            <tr v-for="p in official" :key="p.id">
              <td>{{ p.id }}</td><td>{{ p.screen_code }}</td><td>{{ p.playlist_code }}</td>
              <td>{{ p.window_code }}</td><td>v{{ p.version }}</td>
              <td>
                <span v-if="p.field_ticket_no" class="badge">{{ p.field_ticket_no }}</span>
                <span v-else-if="p.risk_level >= 4" class="badge bad">缺票（不应出现）</span>
                <span v-else class="badge warn">低风险免票</span>
              </td>
              <td>{{ p.summary }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
    <div class="panel">
      <h3>影子草案</h3>
      <table>
        <thead><tr><th>ID</th><th>屏幕</th><th>状态</th><th>场控单号</th><th>摘要</th></tr></thead>
        <tbody>
          <tr v-for="s in shadows" :key="s.id">
            <td>{{ s.id }}</td><td>{{ s.screen_code }}</td><td>{{ s.status }}</td>
            <td>
              <span v-if="s.field_ticket_no" class="badge">{{ s.field_ticket_no }}</span>
              <span v-else-if="s.risk_level >= 4" class="badge bad">待补票</span>
              <span v-else class="badge warn">免票</span>
            </td>
            <td>{{ s.summary }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>`,
  data() {
    return {
      form: { screen_id: 1, playlist_id: 1, window_id: 1, summary: "编排发布", field_ticket_no: "" },
      shadowId: null, shadowTicket: "", official: [], shadows: [], error: "", msg: ""
    };
  },
  async mounted() { await this.reload(); },
  methods: {
    async reload() {
      this.official = (await SB.api("/api/publish/official")).items;
      this.shadows = (await SB.api("/api/publish/shadows")).items;
    },
    async official() {
      this.error = ""; this.msg = "";
      try {
        const r = await SB.api("/api/publish/official", { method: "POST", body: JSON.stringify(this.form) });
        this.msg = "正式发布完成 version=" + r.version + "，场控单号 " + (r.field_ticket_no || "免票");
        await this.reload();
      } catch (e) { this.error = e.message; }
    },
    async shadow() {
      this.error = ""; this.msg = "";
      try {
        const r = await SB.api("/api/publish/shadow", { method: "POST", body: JSON.stringify(this.form) });
        this.msg = "影子已写 id=" + r.id + "（升正前须补票）"; this.shadowId = r.id; await this.reload();
      } catch (e) { this.error = e.message; }
    },
    async supplement() {
      this.error = ""; this.msg = "";
      if (!this.shadowId) { this.error = "请先填影子ID"; return; }
      try {
        const r = await SB.api("/api/publish/shadow/" + this.shadowId + "/ticket", {
          method: "POST", body: JSON.stringify({ field_ticket_no: this.shadowTicket })
        });
        this.msg = "补票完成：" + r.field_ticket_no; await this.reload();
      } catch (e) { this.error = e.message; }
    },
    async promote() {
      this.error = ""; this.msg = "";
      try {
        const payload = this.shadowTicket ? JSON.stringify({ field_ticket_no: this.shadowTicket }) : "{}";
        const r = await SB.api("/api/publish/shadow/" + this.shadowId + "/promote", { method: "POST", body: payload });
        this.msg = "升正完成 version=" + r.version + "，场控单号 " + (r.field_ticket_no || "免票");
        await this.reload();
      } catch (e) { this.error = e.message; }
    }
  }
};
