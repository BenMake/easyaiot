<template>
  <div class="onvif-scan-wrap">
    <Tabs v-model:activeKey="subKey" type="card">
      <TabPane key="task" tab="扫描任务">
        <OnvifScanTaskPanel />
      </TabPane>
      <TabPane key="pwd" tab="密码库">
        <OnvifPasswordLibraryPanel />
      </TabPane>
      <TabPane key="srv" tab="服务器管理">
        <OnvifServerManagePanel />
      </TabPane>
      <TabPane key="blk" tab="IP黑名单">
        <OnvifIpBlacklistPanel />
      </TabPane>
    </Tabs>
  </div>
</template>

<script lang="ts" setup>
import { ref } from 'vue';
import { TabPane, Tabs } from 'ant-design-vue';
import OnvifScanTaskPanel from './OnvifScanTaskPanel.vue';
import OnvifPasswordLibraryPanel from './OnvifPasswordLibraryPanel.vue';
import OnvifServerManagePanel from './OnvifServerManagePanel.vue';
import OnvifIpBlacklistPanel from './OnvifIpBlacklistPanel.vue';

defineOptions({ name: 'OnvifScan' });

const subKey = ref('task');
</script>

<style scoped>
.onvif-scan-wrap {
  padding: 8px 4px 0;
}
</style>
