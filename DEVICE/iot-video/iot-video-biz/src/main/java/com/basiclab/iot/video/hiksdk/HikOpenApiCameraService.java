package com.basiclab.iot.video.hiksdk;

import com.basiclab.iot.video.sdk.dto.HikPlatformAuthRequest;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.hikvision.artemis.sdk.ArtemisHttpUtil;
import com.hikvision.artemis.sdk.config.ArtemisConfig;
import org.springframework.stereotype.Service;

import javax.annotation.Resource;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;

@Service
public class HikOpenApiCameraService {

    private static final String ARTEMIS_PATH = "/artemis";
    private static final String CAMERA_SEARCH_API = ARTEMIS_PATH + "/api/resource/v2/camera/search";

    @Resource
    private ObjectMapper objectMapper;

    public Map<String, Object> queryAllCameras(HikPlatformAuthRequest request) {
        String protocol = request.getProtocol().toLowerCase(Locale.ROOT);
        ArtemisConfig.host = normalizeHost(request.getHost());
        ArtemisConfig.appKey = request.getAppKey();
        ArtemisConfig.appSecret = request.getAppSecret();
        int pageNo = 1;
        int pageSize = 200;
        int total = 0;
        List<Map<String, Object>> cameras = new ArrayList<>();
        while (true) {
            JsonNode root = invokeCameraSearch(protocol, pageNo, pageSize);
            JsonNode dataNode = root.path("data");
            if (total == 0) {
                total = dataNode.path("total").asInt(0);
            }
            JsonNode listNode = dataNode.path("list");
            if (!listNode.isArray() || listNode.size() == 0) {
                break;
            }
            for (JsonNode node : listNode) {
                Map<String, Object> item = new LinkedHashMap<>();
                item.put("cameraIndexCode", text(node, "cameraIndexCode"));
                item.put("cameraName", text(node, "cameraName", "name"));
                item.put("cameraCode", text(node, "cameraCode"));
                item.put("cameraType", text(node, "cameraTypeName", "cameraType"));
                item.put("channelNo", text(node, "channelNo"));
                cameras.add(item);
            }
            if (listNode.size() < pageSize || cameras.size() >= total) {
                break;
            }
            pageNo++;
        }

        Map<String, Object> result = new LinkedHashMap<>();
        result.put("vendor", "hikvision");
        result.put("host", normalizeHost(request.getHost()));
        result.put("total", total);
        result.put("count", cameras.size());
        result.put("list", cameras);
        return result;
    }

    private JsonNode invokeCameraSearch(String protocol, int pageNo, int pageSize) {
        try {
            Map<String, String> path = new HashMap<>(2);
            path.put(protocol + "://", CAMERA_SEARCH_API);

            Map<String, Object> body = new HashMap<>(4);
            body.put("pageNo", pageNo);
            body.put("pageSize", pageSize);
            String result = ArtemisHttpUtil.doPostStringArtemis(
                    path,
                    objectMapper.writeValueAsString(body),
                    null,
                    null,
                    "application/json");
            JsonNode root = objectMapper.readTree(result);
            String code = root.path("code").asText();
            if (!"0".equals(code) && !"200".equals(code)) {
                throw new IllegalStateException("海康平台查询失败, code=" + code + ", msg=" + root.path("msg").asText(""));
            }
            return root;
        } catch (IllegalStateException e) {
            throw e;
        } catch (Exception e) {
            throw new IllegalStateException("海康平台查询异常: " + e.getMessage(), e);
        }
    }

    private static String normalizeHost(String host) {
        String val = host.trim();
        if (val.startsWith("http://")) {
            return val.substring("http://".length());
        }
        if (val.startsWith("https://")) {
            return val.substring("https://".length());
        }
        return val;
    }

    private static String text(JsonNode node, String... fields) {
        for (String field : fields) {
            JsonNode val = node.get(field);
            if (val != null && !val.isNull()) {
                String text = val.asText("");
                if (!text.isEmpty()) {
                    return text;
                }
            }
        }
        return "";
    }
}
