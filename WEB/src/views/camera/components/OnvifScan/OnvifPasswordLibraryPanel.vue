<template>
  <div>
    <BasicTable @register="registerTable">
      <template #toolbar>
        <a-button type="primary" @click="openCreate">
          <template #icon><PlusOutlined /></template>
          新建密码库
        </a-button>
      </template>
      <template #bodyCell="{ column, record }">
        <template v-if="column.dataIndex === 'action'">
          <TableAction
            :actions="[
              { label: '编辑', onClick: () => openEdit(record) },
              {
                label: '删除',
                color: 'error',
                popConfirm: { title: '确认删除？', confirm: () => handleDelete(record) },
              },
            ]"
          />
        </template>
      </template>
    </BasicTable>

    <a-modal
      v-model:open="modalOpen"
      :title="editingId ? '编辑密码库' : '新建密码库'"
      :width="560"
      :confirmLoading="saving"
      @ok="handleSave"
    >
      <a-form :label-col="{ span: 6 }" :wrapper-col="{ span: 16 }" class="pt-2">
        <a-form-item label="名称" required>
          <a-input v-model:value="form.name" />
        </a-form-item>
        <a-form-item label="编码 lib_code" :required="!editingId">
          <a-input v-model:value="form.lib_code" :disabled="!!editingId" placeholder="唯一，创建后不可改" />
        </a-form-item>
        <a-form-item label="说明">
          <a-input v-model:value="form.description" />
        </a-form-item>
        <a-form-item label="凭据 JSON" required>
          <a-textarea
            v-model:value="form.credentialsJson"
            :rows="10"
            placeholder='[{"username":"admin","password":"xxx"}, ...]'
          />
        </a-form-item>
      </a-form>
    </a-modal>
  </div>
</template>

<script lang="ts" setup>
import { reactive, ref } from 'vue';
import { PlusOutlined } from '@ant-design/icons-vue';
import { BasicTable, TableAction, useTable } from '@/components/Table';
import { useMessage } from '@/hooks/web/useMessage';
import type { BasicColumn } from '@/components/Table';
import {
  createOnvifPasswordLibrary,
  deleteOnvifPasswordLibrary,
  getOnvifPasswordLibrary,
  listOnvifPasswordLibraries,
  updateOnvifPasswordLibrary,
} from '@/api/device/onvif_scan';

const { createMessage } = useMessage();

const columns: BasicColumn[] = [
  { title: 'ID', dataIndex: 'id', width: 60 },
  { title: '名称', dataIndex: 'name', width: 140 },
  { title: '编码', dataIndex: 'lib_code', width: 120 },
  { title: '凭据条数', dataIndex: 'credential_count', width: 90 },
  { title: '操作', dataIndex: 'action', width: 120, fixed: 'right' },
];

async function fetchList(params: Record<string, any>) {
  const res: any = await listOnvifPasswordLibraries({
    pageNo: params.page,
    pageSize: params.pageSize,
  });
  return { list: res.data ?? [], total: res.total ?? 0 };
}

const [registerTable, { reload }] = useTable({
  title: 'ONVIF 密码库',
  api: fetchList,
  columns,
  pagination: true,
  rowKey: 'id',
});

const modalOpen = ref(false);
const saving = ref(false);
const editingId = ref<number | null>(null);
const form = reactive({
  name: '',
  lib_code: '',
  description: '',
  credentialsJson: '[{"username":"admin","password":""}]',
});

function openCreate() {
  editingId.value = null;
  form.name = '';
  form.lib_code = '';
  form.description = '';
  form.credentialsJson = '[{"username":"admin","password":""}]';
  modalOpen.value = true;
}

async function openEdit(record: any) {
  editingId.value = record.id;
  try {
    const res: any = await getOnvifPasswordLibrary(record.id, true);
    const d = res?.lib_code !== undefined ? res : res?.data ?? {};
    form.name = d.name || '';
    form.lib_code = d.lib_code || '';
    form.description = d.description || '';
    form.credentialsJson = JSON.stringify(d.credentials || [], null, 2);
    modalOpen.value = true;
  } catch (e) {
    console.error(e);
  }
}

async function handleSave() {
  let creds: any[];
  try {
    creds = JSON.parse(form.credentialsJson || '[]');
    if (!Array.isArray(creds)) throw new Error('须为数组');
  } catch {
    createMessage.error('凭据 JSON 格式不正确');
    return;
  }
  if (!form.name.trim()) {
    createMessage.warning('请填写名称');
    return;
  }
  if (!editingId.value && !form.lib_code.trim()) {
    createMessage.warning('请填写 lib_code');
    return;
  }
  saving.value = true;
  try {
    if (editingId.value) {
      await updateOnvifPasswordLibrary(editingId.value, {
        name: form.name.trim(),
        description: form.description,
        credentials: creds,
      });
    } else {
      await createOnvifPasswordLibrary({
        name: form.name.trim(),
        lib_code: form.lib_code.trim(),
        description: form.description,
        credentials: creds,
      });
    }
    createMessage.success('已保存');
    modalOpen.value = false;
    reload();
  } catch (e) {
    console.error(e);
  } finally {
    saving.value = false;
  }
}

async function handleDelete(record: any) {
  try {
    await deleteOnvifPasswordLibrary(record.id);
    createMessage.success('已删除');
    reload();
  } catch (e) {
    console.error(e);
  }
}
</script>
