using UnityEngine;

public class OrbitCamera : MonoBehaviour
{
    public Transform target; // Object to orbit around
    public float distance = 10f;
    public float xSpeed = 120f;
    public float ySpeed = 120f;
    public float yMinLimit = -20f;
    public float yMaxLimit = 80f;
    public float distanceMin = 2f;
    public float distanceMax = 20f;
    public float scrollSpeed = 5f;
    public float pinchSpeed = 2f; // Speed of pinch zoom
    
    private float x = 0f;
    private float y = 0f;
    private bool isRotating = false;
    private float lastPinchDistance = 0f;

    void Start()
    {
        Vector3 angles = transform.eulerAngles;
        x = angles.y;
        y = angles.x;
        
        // If no target assigned, create empty GameObject at origin
        if (target == null)
        {
            GameObject targetObj = new GameObject("CameraTarget");
            targetObj.transform.position = Vector3.zero;
            target = targetObj.transform;
        }
    }

    void LateUpdate()
    {
        if (target)
        {
            HandleInput();
            UpdateCameraPosition();
        }
    }
    
    void HandleInput()
    {
        // Handle touch input for mobile
        if (Input.touchCount == 1)
        {
            // Single touch - rotation
            Touch touch = Input.GetTouch(0);
            
            if (touch.phase == TouchPhase.Began)
            {
                isRotating = true;
            }
            else if (touch.phase == TouchPhase.Ended || touch.phase == TouchPhase.Canceled)
            {
                isRotating = false;
            }
            else if (touch.phase == TouchPhase.Moved && isRotating)
            {
                Vector2 touchDelta = touch.deltaPosition;
                x += touchDelta.x * xSpeed * distance * 0.0001f;
                y -= touchDelta.y * ySpeed * 0.0001f;
            }
        }
        else if (Input.touchCount == 2)
        {
            // Two touches - pinch zoom
            isRotating = false; // Stop rotation when pinching
            
            Touch touch1 = Input.GetTouch(0);
            Touch touch2 = Input.GetTouch(1);
            
            // Get current distance between fingers
            float currentPinchDistance = Vector2.Distance(touch1.position, touch2.position);
            
            if (touch1.phase == TouchPhase.Began || touch2.phase == TouchPhase.Began)
            {
                lastPinchDistance = currentPinchDistance;
            }
            else if (touch1.phase == TouchPhase.Moved || touch2.phase == TouchPhase.Moved)
            {
                if (lastPinchDistance > 0)
                {
                    // Calculate zoom based on pinch distance change
                    float deltaDistance = lastPinchDistance - currentPinchDistance;
                    distance += deltaDistance * pinchSpeed * 0.01f;
                    distance = Mathf.Clamp(distance, distanceMin, distanceMax);
                }
                lastPinchDistance = currentPinchDistance;
            }
        }
        else
        {
            // Mouse input for desktop
            if (Input.GetMouseButtonDown(0))
            {
                isRotating = true;
            }
            
            if (Input.GetMouseButtonUp(0))
            {
                isRotating = false;
            }
            
            if (isRotating)
            {
                x += Input.GetAxis("Mouse X") * xSpeed * distance * 0.02f;
                y -= Input.GetAxis("Mouse Y") * ySpeed * 0.02f;
            }
            
            // Mouse wheel zoom
            distance -= Input.GetAxis("Mouse ScrollWheel") * scrollSpeed;
            distance = Mathf.Clamp(distance, distanceMin, distanceMax);
        }
    }
    
    void UpdateCameraPosition()
    {
        y = ClampAngle(y, yMinLimit, yMaxLimit);
        
        Quaternion rotation = Quaternion.Euler(y, x, 0);
        
        Vector3 negDistance = new Vector3(0.0f, 0.0f, -distance);
        Vector3 position = rotation * negDistance + target.position;
        
        transform.rotation = rotation;
        transform.position = position;
    }
    
    public static float ClampAngle(float angle, float min, float max)
    {
        if (angle < -360F)
            angle += 360F;
        if (angle > 360F)
            angle -= 360F;
        return Mathf.Clamp(angle, min, max);
    }
}