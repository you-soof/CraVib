using System.Collections;
using System.Collections.Generic;
using TMPro;
using UnityEngine;
using UnityEngine.UI;
using UnityEngine.Networking;

public class CrackDetectionUI : MonoBehaviour
{
    [Header("UI References")]
    public TextMeshProUGUI vibrationStatusText;
    public ScrollRect crackScrollView;
    public Transform crackListContent;
    public Button acknowledgeButton;
    public Button silenceButton;
    public Image statusIndicator;
    public GameObject crackItemPrefab;

    [Header("Colors")]
    public Color normalColor = Color.green;
    public Color warningColor = Color.yellow;
    public Color criticalColor = Color.red;
    public Color silencedColor = Color.gray;

    [Header("Status Messages")]
    public TextMeshProUGUI statusMessageText;
    
    [Header("Vibration Threshold")]
    public float vibrationThreshold = 10f; // Make sure this matches SHMManager threshold

    private List<GameObject> crackItems = new();
    private AlertStatus currentStatus = AlertStatus.Normal;
    private bool isSilenced = false;

    private void Start()
    {
        acknowledgeButton.onClick.AddListener(AcknowledgeAlert);
        silenceButton.onClick.AddListener(ToggleSilence);

        SHMEvents.OnVibrationDataReceived += UpdateVibrationStatus;
        SHMEvents.OnCrackDataReceived += UpdateCrackList;
        SHMEvents.OnDataError += HandleDataError;

        UpdateStatusIndicator(AlertStatus.Normal);
        
        // Initialize status message
        if (statusMessageText != null)
            statusMessageText.text = "Monitoring for cracks...";
    }

    private void UpdateVibrationStatus(VibrationData[] vibrations)
    {
        if (vibrations == null || vibrations.Length == 0)
        {
            vibrationStatusText.text = "No vibration data";
            return;
        }

        var latest = GetLatest(vibrations);
        float mag = latest.Magnitude;

        vibrationStatusText.text = $"Vibration: {mag:F2} m/s²\nX: {latest.x:F2} Y: {latest.y:F2} Z: {latest.z:F2}\n{latest.Time:HH:mm:ss}";

        // Update status indicator based on vibration magnitude
        if (!isSilenced)
        {
            if (mag > vibrationThreshold)
            {
                SetStatus(AlertStatus.Critical);
                Debug.Log($"UI: Vibration {mag:F2} > {vibrationThreshold} - Setting CRITICAL status");
            }
            else
            {
                SetStatus(AlertStatus.Normal);
                Debug.Log($"UI: Vibration {mag:F2} <= {vibrationThreshold} - Setting NORMAL status");
            }
        }
    }

    private void UpdateCrackList(CrackData[] cracks)
    {
        Debug.Log($"UI: Updating crack list with {(cracks?.Length ?? 0)} cracks");
        
        ClearCrackList();

        if (cracks == null || cracks.Length == 0)
        {
            if (statusMessageText != null)
                statusMessageText.text = $"No cracks detected - Last checked: {System.DateTime.Now:HH:mm:ss}";
            return;
        }

        if (statusMessageText != null)
            statusMessageText.text = $"Found {cracks.Length} crack(s) - Last updated: {System.DateTime.Now:HH:mm:ss}";

        foreach (var crack in cracks)
        {
            Debug.Log($"UI: Creating crack item for timestamp {crack.timestamp}, score {crack.score}");
            
            GameObject item = Instantiate(crackItemPrefab, crackListContent);
            
            // Try multiple ways to find text components for better compatibility
            SetCrackItemText(item, "TimeText", crack.Time.ToString("HH:mm:ss"));
            SetCrackItemText(item, "ScoreText", $"Score: {crack.score:F1}");

            // Set item color based on criticality
            var itemImage = item.GetComponent<Image>();
            if (itemImage != null)
                itemImage.color = crack.IsCritical ? criticalColor : warningColor;

            // Setup image button
            SetupImageButton(item, crack.image_url);

            crackItems.Add(item);

            // Set alert status if crack is critical
            if (crack.IsCritical && !isSilenced)
            {
                SetStatus(AlertStatus.Critical);
            }
            else if (!isSilenced && currentStatus == AlertStatus.Normal)
            {
                SetStatus(AlertStatus.Warning);
            }
        }

        // Force UI update and scroll to bottom
        if (crackScrollView != null)
        {
            StartCoroutine(ScrollToBottom());
        }
    }

    private void SetCrackItemText(GameObject item, string childName, string text)
    {
        // Try to find the text component in various ways
        Transform textTransform = item.transform.Find(childName);
        if (textTransform != null)
        {
            // Try Text component first
            var textComponent = textTransform.GetComponent<Text>();
            if (textComponent != null)
            {
                textComponent.text = text;
                return;
            }
            
            // Try TextMeshProUGUI component
            var tmpComponent = textTransform.GetComponent<TextMeshProUGUI>();
            if (tmpComponent != null)
            {
                tmpComponent.text = text;
                return;
            }
        }
        
        Debug.LogWarning($"Could not find text component '{childName}' in crack item");
    }

    private void SetupImageButton(GameObject item, string imageUrl)
    {
        var imgBtn = item.transform.Find("ImageButton")?.GetComponent<Button>();
        if (imgBtn != null)
        {
            imgBtn.onClick.RemoveAllListeners(); // Clear any existing listeners
            imgBtn.onClick.AddListener(() => StartCoroutine(LoadAndShowImage(imageUrl)));
            
            // Update button text
            SetCrackItemText(imgBtn.gameObject, "Text", "View Image");
        }
    }

    private IEnumerator ScrollToBottom()
    {
        yield return new WaitForEndOfFrame();
        Canvas.ForceUpdateCanvases();
        crackScrollView.verticalNormalizedPosition = 0f;
    }

    private IEnumerator LoadAndShowImage(string url)
    {
        Debug.Log($"Loading crack image from: {url}");
        
        using UnityWebRequest req = UnityWebRequestTexture.GetTexture(url);
        req.timeout = 15; // Longer timeout for image loading
        req.SetRequestHeader("Cache-Control", "no-cache");
        yield return req.SendWebRequest();

        if (req.result == UnityWebRequest.Result.Success)
        {
            Texture2D tex = DownloadHandlerTexture.GetContent(req);
            ShowImagePopup(tex);
            Debug.Log("Crack image loaded successfully");
        }
        else
        {
            Debug.LogError($"Failed to load crack image: {req.error}");
            ShowErrorPopup($"Failed to load image: {req.error}");
        }
    }

    private void ShowImagePopup(Texture2D tex)
    {
        // Create popup canvas
        GameObject popup = new GameObject("CrackImagePopup");
        Canvas canvas = popup.AddComponent<Canvas>();
        canvas.renderMode = RenderMode.ScreenSpaceOverlay;
        canvas.sortingOrder = 100;
        
        // Add CanvasScaler for better scaling
        CanvasScaler scaler = popup.AddComponent<CanvasScaler>();
        scaler.uiScaleMode = CanvasScaler.ScaleMode.ScaleWithScreenSize;
        scaler.referenceResolution = new Vector2(1920, 1080);
        
        // Add GraphicRaycaster for UI interactions
        popup.AddComponent<GraphicRaycaster>();

        // Create background panel
        GameObject bgPanel = new GameObject("BackgroundPanel");
        bgPanel.transform.SetParent(popup.transform);
        Image bgImage = bgPanel.AddComponent<Image>();
        bgImage.color = new Color(0, 0, 0, 0.8f); // Semi-transparent black
        RectTransform bgRect = bgImage.rectTransform;
        bgRect.anchorMin = Vector2.zero;
        bgRect.anchorMax = Vector2.one;
        bgRect.offsetMin = Vector2.zero;
        bgRect.offsetMax = Vector2.zero;

        // Create image display
        GameObject imageObj = new GameObject("CrackImage");
        imageObj.transform.SetParent(bgPanel.transform);
        RawImage img = imageObj.AddComponent<RawImage>();
        img.texture = tex;
        
        RectTransform imgRect = img.rectTransform;
        imgRect.anchorMin = new Vector2(0.5f, 0.5f);
        imgRect.anchorMax = new Vector2(0.5f, 0.5f);
        imgRect.pivot = new Vector2(0.5f, 0.5f);
        imgRect.sizeDelta = new Vector2(600, 600); // Larger size for better viewing
        imgRect.anchoredPosition = Vector2.zero;

        // Add close button
        CreateCloseButton(bgPanel, popup);

        // Auto-close after 15 seconds
        Destroy(popup, 15f);
    }

    private void CreateCloseButton(GameObject parent, GameObject popup)
    {
        GameObject closeBtn = new GameObject("CloseButton");
        closeBtn.transform.SetParent(parent.transform);
        Button btnComponent = closeBtn.AddComponent<Button>();
        Image btnImage = closeBtn.AddComponent<Image>();
        btnImage.color = Color.red;
        
        RectTransform btnRect = btnComponent.transform as RectTransform;
        btnRect.anchorMin = new Vector2(1f, 1f);
        btnRect.anchorMax = new Vector2(1f, 1f);
        btnRect.pivot = new Vector2(1f, 1f);
        btnRect.sizeDelta = new Vector2(60, 60);
        btnRect.anchoredPosition = new Vector2(-20, -20);

        // Close button text
        GameObject btnTextObj = new GameObject("Text");
        btnTextObj.transform.SetParent(closeBtn.transform);
        Text btnText = btnTextObj.AddComponent<Text>();
        btnText.text = "✕";
        btnText.font = Resources.GetBuiltinResource<Font>("Arial.ttf");
        btnText.fontSize = 24;
        btnText.color = Color.white;
        btnText.alignment = TextAnchor.MiddleCenter;
        
        RectTransform btnTextRect = btnText.rectTransform;
        btnTextRect.anchorMin = Vector2.zero;
        btnTextRect.anchorMax = Vector2.one;
        btnTextRect.offsetMin = Vector2.zero;
        btnTextRect.offsetMax = Vector2.zero;

        // Setup close functionality
        btnComponent.onClick.AddListener(() => Destroy(popup));
    }

    private void ShowErrorPopup(string errorMessage)
    {
        Debug.LogError(errorMessage);
        if (statusMessageText != null)
            statusMessageText.text = $"Image load error: {errorMessage}";
    }

    private void SetStatus(AlertStatus status)
    {
        currentStatus = status;
        UpdateStatusIndicator(status);
    }

    private void UpdateStatusIndicator(AlertStatus status)
    {
        if (statusIndicator != null)
        {
            statusIndicator.color = status switch
            {
                AlertStatus.Warning => warningColor,
                AlertStatus.Critical => criticalColor,
                AlertStatus.Silenced => silencedColor,
                _ => normalColor
            };
        }
    }

    private void AcknowledgeAlert()
    {
        SetStatus(AlertStatus.Normal);
        isSilenced = false;
        
        // Notify SHMManager about acknowledgment
        SHMEvents.OnAlertAcknowledged?.Invoke();
        
        if (statusMessageText != null)
            statusMessageText.text = "Alert acknowledged - Wall movement stopped, light continues";
    }

    private void ToggleSilence()
    {
        isSilenced = !isSilenced;
        UpdateStatusIndicator(isSilenced ? AlertStatus.Silenced : currentStatus);
        
        // Notify SHMManager about silence state
        SHMEvents.OnSilenceToggled?.Invoke(isSilenced);
        
        if (statusMessageText != null)
            statusMessageText.text = isSilenced ? "All alerts silenced" : "Alerts active";
    }

    private void HandleDataError(string error)
    {
        vibrationStatusText.text = $"Error: {error}";
        UpdateStatusIndicator(AlertStatus.Critical);
        
        if (statusMessageText != null)
            statusMessageText.text = $"Data Error: {error}";
    }

    private void ClearCrackList()
    {
        foreach (var item in crackItems) 
        {
            if (item != null) 
                Destroy(item);
        }
        crackItems.Clear();
    }

    private VibrationData GetLatest(VibrationData[] vibrations)
    {
        VibrationData latest = vibrations[0];
        foreach (var v in vibrations)
            if (v.Time > latest.Time)
                latest = v;
        return latest;
    }

    private void OnDestroy()
    {
        SHMEvents.OnVibrationDataReceived -= UpdateVibrationStatus;
        SHMEvents.OnCrackDataReceived -= UpdateCrackList;
        SHMEvents.OnDataError -= HandleDataError;
    }
}