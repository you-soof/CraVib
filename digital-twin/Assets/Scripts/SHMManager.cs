using System.Collections;
using UnityEngine;
using UnityEngine.Networking;
using System;

public class SHMManager : MonoBehaviour
{
    [Header("Setup")]
    public GameObject wall;
    public string crackToken;
    public string vibrationURL;
    public string vibrationBaseURL; // Optional: for timestamp-based vibration checking
    public string crackBaseURL = "https://cravib.blob.core.windows.net/crack/";
    public Material normalMat, alertMat;
    public Light alertLight;

    [Header("Settings")]
    public float updateInterval = 5f;
    public float vibrationThreshold = 10f;
    public float flashRate = 2f;
    [Range(1, 10)]
    public int crackCheckRange = 1; // Check for crack images within last X minutes
    public bool useTimestampVibration = false; // Toggle between URL and timestamp-based vibration checking

    private Vector3 originalPos;
    private Coroutine flashRoutine;
    private Coroutine vibrateRoutine;
    private bool isSilenced = false;
    private bool isAcknowledged = false;

    void Start()
    {
        originalPos = wall.transform.position;
        
        // Subscribe to UI events
        SHMEvents.OnSilenceToggled += HandleSilenceToggled;
        SHMEvents.OnAlertAcknowledged += HandleAlertAcknowledged;
        
        StartCoroutine(UpdateLoop());
    }

    IEnumerator UpdateLoop()
    {
        while (true)
        {
            if (useTimestampVibration && !string.IsNullOrEmpty(vibrationBaseURL))
            {
                yield return FetchCurrentVibration();
            }
            else
            {
                yield return FetchVibration();
            }
            
            yield return FetchCurrentCracks();
            yield return new WaitForSeconds(updateInterval);
        }
    }

    IEnumerator FetchVibration()
    {
        Debug.Log($"Fetching vibration data from: {vibrationURL}");
        
        using UnityWebRequest req = UnityWebRequest.Get(vibrationURL);
        req.timeout = 10; // Increase timeout for WebGL
        req.SetRequestHeader("Cache-Control", "no-cache"); // Prevent caching issues
        
        yield return req.SendWebRequest();
        
        Debug.Log($"Vibration Request URL: {vibrationURL}");
        Debug.Log($"Vibration Response Code: {req.responseCode}");
        Debug.Log($"Vibration Response: {req.downloadHandler.text}");

        if (req.result != UnityWebRequest.Result.Success)
        {
            Debug.LogError($"Vibration fetch failed: {req.error}");
            SHMEvents.OnDataError?.Invoke(req.error);
            yield break;
        }

        try
        {
            var data = JsonUtility.FromJson<VibrationDataArray>("{\"vibrations\":" + req.downloadHandler.text + "}");
            SHMEvents.OnVibrationDataReceived?.Invoke(data.vibrations);
            ProcessVibrationData(data.vibrations);
        }
        catch (System.Exception e)
        {
            Debug.LogError($"Failed to parse vibration data: {e.Message}");
            SHMEvents.OnDataError?.Invoke($"Vibration data parse error: {e.Message}");
        }
    }

    IEnumerator FetchCurrentVibration()
    {
        // Check for current timestamp vibration data (similar to crack checking)
        DateTime currentTime = DateTime.Now;
        string timestamp = currentTime.ToString("yyyy-MM-dd_HH-mm-ss");
        string vibrationFileName = $"vibration_{timestamp}.json"; // Adjust filename format as needed
        string fullVibrationUrl = vibrationBaseURL + vibrationFileName;

        Debug.Log($"Checking for current vibration data: {fullVibrationUrl}");

        using UnityWebRequest req = UnityWebRequest.Get(fullVibrationUrl);
        req.timeout = 5; // Shorter timeout for timestamp checks
        req.SetRequestHeader("Cache-Control", "no-cache");
        yield return req.SendWebRequest();

        if (req.result == UnityWebRequest.Result.Success)
        {
            Debug.Log($"Current vibration data found: {req.downloadHandler.text}");
            
            try
            {
                var data = JsonUtility.FromJson<VibrationDataArray>("{\"vibrations\":" + req.downloadHandler.text + "}");
                SHMEvents.OnVibrationDataReceived?.Invoke(data.vibrations);
                ProcessVibrationData(data.vibrations);
            }
            catch (System.Exception e)
            {
                Debug.LogError($"Failed to parse vibration data: {e.Message}");
                SHMEvents.OnDataError?.Invoke($"Vibration data parse error: {e.Message}");
            }
        }
        else
        {
            Debug.Log($"No current vibration data found for timestamp: {timestamp}");
            // Optionally create empty vibration data or handle as no data
            SHMEvents.OnVibrationDataReceived?.Invoke(new VibrationData[0]);
        }
    }

    private void ProcessVibrationData(VibrationData[] vibrations)
    {
        // Visual alert handling (e.g., wall vibrate)
        if (vibrations.Length > 0)
        {
            var vib = vibrations[^1];
            float mag = vib.Magnitude;

            Debug.Log($"Processing vibration magnitude: {mag}, threshold: {vibrationThreshold}");

            if (mag > vibrationThreshold)
            {
                // RED - Alert state
                wall.GetComponent<Renderer>().material = alertMat;
                
                // Handle wall vibration based on silence/acknowledge state
                if (!isSilenced && !isAcknowledged)
                {
                    if (vibrateRoutine != null) StopCoroutine(vibrateRoutine);
                    vibrateRoutine = StartCoroutine(Vibrate(wall, vib.Acceleration.normalized * 0.05f));
                }
                else if (isAcknowledged) // Acknowledged but not silenced - stop wall movement
                {
                    if (vibrateRoutine != null) 
                    {
                        StopCoroutine(vibrateRoutine);
                        vibrateRoutine = null;
                    }
                    wall.transform.position = originalPos;
                }

                // Handle light flashing based on silence state
                if (alertLight && !isSilenced)
                {
                    if (flashRoutine == null)
                        flashRoutine = StartCoroutine(FlashLight());
                }
                else if (isSilenced) // Silenced - stop light
                {
                    if (alertLight)
                    {
                        alertLight.enabled = false;
                        if (flashRoutine != null) 
                        {
                            StopCoroutine(flashRoutine);
                            flashRoutine = null;
                        }
                    }
                }
            }
            else
            {
                // GREEN - Normal state (below threshold)
                Debug.Log("Vibration below threshold - setting to normal state");
                wall.GetComponent<Renderer>().material = normalMat;
                wall.transform.position = originalPos;
                
                // Stop all alert activities
                if (vibrateRoutine != null) 
                {
                    StopCoroutine(vibrateRoutine);
                    vibrateRoutine = null;
                }
                
                if (alertLight)
                {
                    alertLight.enabled = false;
                    if (flashRoutine != null) 
                    {
                        StopCoroutine(flashRoutine);
                        flashRoutine = null;
                    }
                }
            }
        }
        else
        {
            Debug.Log("No vibration data - resetting to normal state");
            // No vibration data - reset to normal
            ResetAlerts();
        }
    }

    IEnumerator FetchCurrentCracks()
    {
        // Generate timestamps for the last few minutes to check for crack images
        DateTime currentTime = DateTime.Now;
        var cracksFound = new System.Collections.Generic.List<CrackData>();

        // Check for crack images within the specified time range
        for (int i = 0; i < crackCheckRange; i++)
        {
            DateTime checkTime = currentTime.AddMinutes(-i);
            string timestamp = checkTime.ToString("yyyy-MM-dd_HH-mm-ss");
            string crackFileName = $"crack_{timestamp}.jpg";
            string fullCrackUrl = crackBaseURL + crackFileName;

            Debug.Log($"Checking for crack image: {fullCrackUrl}");

            // Use GET request instead of HEAD for better WebGL compatibility
            yield return StartCoroutine(CheckCrackImageWebGL(fullCrackUrl, timestamp, cracksFound));
        }

        // Always send crack data to UI, even if empty
        Debug.Log($"Found {cracksFound.Count} crack images");
        SHMEvents.OnCrackDataReceived?.Invoke(cracksFound.ToArray());
    }

    IEnumerator CheckCrackImageWebGL(string imageUrl, string timestamp, System.Collections.Generic.List<CrackData> cracksFound)
    {
        // Use GET request instead of HEAD for WebGL compatibility
        using UnityWebRequest req = UnityWebRequest.Get(imageUrl);
        req.timeout = 5; // Short timeout
        req.SetRequestHeader("Cache-Control", "no-cache");
        yield return req.SendWebRequest();

        if (req.result == UnityWebRequest.Result.Success && req.responseCode == 200)
        {
            Debug.Log($"Found crack image: {imageUrl}");
            
            // Create crack data for found image
            var crackData = new CrackData
            {
                timestamp = timestamp,
                score = UnityEngine.Random.Range(0.5f, 1.0f), // You might want to get this from somewhere else
                image_url = imageUrl
            };
            
            cracksFound.Add(crackData);
        }
        else
        {
            // Image doesn't exist - this is normal, not an error
            Debug.Log($"No crack image found for timestamp: {timestamp} (Response: {req.responseCode})");
        }
    }

    IEnumerator Vibrate(GameObject obj, Vector3 intensity)
    {
        float time = 0;
        while (true)
        {
            obj.transform.position = originalPos + intensity * Mathf.Sin(time * 10f);
            time += Time.deltaTime;
            yield return null;
        }
    }

    IEnumerator FlashLight()
    {
        while (true)
        {
            if (alertLight != null)
            {
                alertLight.enabled = !alertLight.enabled;
                if (alertLight.enabled)
                {
                    alertLight.color = Color.red;
                    alertLight.intensity = 5f;
                }
            }
            yield return new WaitForSeconds(1f / flashRate);
        }
    }

    private void HandleSilenceToggled(bool silenced)
    {
        isSilenced = silenced;
        
        if (silenced)
        {
            // Stop both wall movement and light flashing
            if (vibrateRoutine != null) 
            {
                StopCoroutine(vibrateRoutine);
                vibrateRoutine = null;
            }
            wall.transform.position = originalPos;
            
            if (alertLight)
            {
                alertLight.enabled = false;
                if (flashRoutine != null) 
                {
                    StopCoroutine(flashRoutine);
                    flashRoutine = null;
                }
            }
        }
        // If unsilenced, the next vibration check will restart alerts if needed
    }

    private void HandleAlertAcknowledged()
    {
        isAcknowledged = true;
        
        // Stop wall movement but keep light blinking if there's still an alert
        if (vibrateRoutine != null) 
        {
            StopCoroutine(vibrateRoutine);
            vibrateRoutine = null;
        }
        wall.transform.position = originalPos;
        
        // Reset acknowledged state after a delay so new alerts can trigger wall movement
        StartCoroutine(ResetAcknowledgedState());
    }

    private IEnumerator ResetAcknowledgedState()
    {
        yield return new WaitForSeconds(30f); // Reset after 30 seconds
        isAcknowledged = false;
    }

    private void ResetAlerts()
    {
        wall.GetComponent<Renderer>().material = normalMat;
        wall.transform.position = originalPos;
        
        if (vibrateRoutine != null) 
        {
            StopCoroutine(vibrateRoutine);
            vibrateRoutine = null;
        }
        
        if (alertLight)
        {
            alertLight.enabled = false;
            if (flashRoutine != null) 
            {
                StopCoroutine(flashRoutine);
                flashRoutine = null;
            }
        }
        
        // Reset states when no alerts
        isSilenced = false;
        isAcknowledged = false;
    }

    private void OnDestroy()
    {
        // Unsubscribe from events
        SHMEvents.OnSilenceToggled -= HandleSilenceToggled;
        SHMEvents.OnAlertAcknowledged -= HandleAlertAcknowledged;
    }
}