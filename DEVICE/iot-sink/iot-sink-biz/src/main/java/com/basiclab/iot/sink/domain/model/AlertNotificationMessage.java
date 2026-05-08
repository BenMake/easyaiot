package com.basiclab.iot.sink.domain.model;

import com.fasterxml.jackson.annotation.JsonAlias;
import lombok.Data;

import java.util.List;
import java.util.Map;

/**
 * 告警通知消息DTO（用于Kafka消息传输）
 *
 * @author 翱翔的雄库鲁
 * @email andywebjava@163.com
 * @wechat EasyAIoT2025
 */
@Data
public class AlertNotificationMessage {
    
    /**
     * 告警ID
     */
    @JsonAlias("alert_id")
    private Integer alertId;
    
    /**
     * 任务ID
     */
    @JsonAlias("task_id")
    private Integer taskId;
    
    /**
     * 任务名称
     */
    @JsonAlias("task_name")
    private String taskName;
    
    /**
     * 设备ID
     */
    @JsonAlias("device_id")
    private String deviceId;
    
    /**
     * 设备名称
     */
    @JsonAlias("device_name")
    private String deviceName;
    
    /**
     * 告警信息
     */
    private AlertInfo alert;
    
    /**
     * 通知人列表
     */
    private List<Map<String, Object>> notifyUsers;
    
    /**
     * 通知方式列表
     */
    private List<String> notifyMethods;
    
    /**
     * 通知渠道和模板配置列表
     */
    private List<Map<String, Object>> channels;
    
    /**
     * 时间戳
     */
    private String timestamp;
    
    /**
     * 是否需要发送通知
     * true: 需要发送通知（有通知配置且通知人列表不为空）
     * false: 不需要发送通知（没有通知配置或通知人列表为空）
     */
    private Boolean shouldNotify;

    /**
     * 是否开启了人脸检测（用于人脸ODS下沉分流）
     */
    private Boolean faceDetectionEnabled;

    /**
     * 是否开启了车牌检测（用于车牌ODS下沉分流）
     */
    private Boolean plateDetectionEnabled;
    
    /**
     * 告警信息内部类
     */
    @Data
    public static class AlertInfo {
        private String object;
        private String event;
        private String region;
        private Object information;
        /** Python 端也可能传 snake_case */
        @JsonAlias("image_path")
        private String imagePath;
        @JsonAlias("record_path")
        private String recordPath;
        private String time;
        @JsonAlias("task_type")
        private String taskType;  // 告警事件类型[realtime:实时算法任务,snap:抓拍算法任务]
    }
}

