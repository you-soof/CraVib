using System;
using UnityEngine;

[Serializable]
public class VibrationData
{
    public string timestamp;
    public float x, y, z;

    public Vector3 Acceleration => new(x, y, z);
    public float Magnitude => Mathf.Sqrt(x * x + y * y + z * z);
    public DateTime Time
    {
        get
        {
            if (string.IsNullOrEmpty(timestamp))
                return DateTime.Now;
            
            try
            {
                return DateTime.ParseExact(timestamp, "yyyy-MM-dd_HH-mm-ss", null);
            }
            catch (FormatException)
            {
                Debug.LogWarning($"Invalid timestamp format: {timestamp}");
                return DateTime.MinValue;
            }
        }
    }
}

[Serializable]
public class CrackData
{
    public string timestamp;
    public float score;
    public string image_url;

    public DateTime Time
    {
        get
        {
            if (string.IsNullOrEmpty(timestamp))
                return DateTime.Now;
            
            try
            {
                return DateTime.ParseExact(timestamp, "yyyy-MM-dd_HH-mm-ss", null);
            }
            catch (FormatException)
            {
                Debug.LogWarning($"Invalid timestamp format: {timestamp}");
                return DateTime.MinValue;
            }
        }
    }
    public bool IsCritical => score > 0.7f;
}

[Serializable] public class VibrationDataArray { public VibrationData[] vibrations; }
[Serializable] public class CrackDataArray { public CrackData[] cracks; }

public enum AlertStatus
{
    Normal, 
    Warning, 
    Critical, 
    Silenced 
    
}