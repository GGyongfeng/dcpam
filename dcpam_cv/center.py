import os
from datetime import datetime

import cv2
import matplotlib.pyplot as plt
import numpy as np
from scipy import optimize

def centroid_method(img, threshold_ratio=0.5):
    """使用重心法计算光斑中心"""
    max_val = np.max(img)
    threshold = max_val * threshold_ratio
    mask = img > threshold
    
    if not np.any(mask):
        return None, None
    
    y_coords, x_coords = np.where(mask)
    intensities = img[y_coords, x_coords]
    
    total_intensity = np.sum(intensities)
    if total_intensity == 0:
        return None, None
    
    x_center = np.sum(x_coords * intensities) / total_intensity
    y_center = np.sum(y_coords * intensities) / total_intensity
    
    return x_center, y_center

def gaussian_fit(img, initial_guess=None):
    """使用二维高斯函数拟合光斑中心"""
    h, w = img.shape
    y, x = np.mgrid[:h, :w]
    
    if initial_guess is None:
        x0, y0 = centroid_method(img)
        if x0 is None:
            x0, y0 = w//2, h//2
    else:
        x0, y0 = initial_guess
    
    x_data = np.vstack((x.ravel(), y.ravel()))
    y_data = img.ravel()
    
    def gaussian_2d(xy, amplitude, x0, y0, sigma_x, sigma_y, offset):
        x, y = xy
        return amplitude * np.exp(-((x-x0)**2/(2*sigma_x**2) + (y-y0)**2/(2*sigma_y**2))) + offset
    
    max_val = np.max(img)
    min_val = np.min(img)
    initial_params = [max_val-min_val, x0, y0, 10, 10, min_val]
    
    try:
        popt, _ = optimize.curve_fit(gaussian_2d, x_data, y_data, p0=initial_params, maxfev=5000)
        x_center, y_center = popt[1], popt[2]
        return x_center, y_center, popt
    except:
        return x0, y0, None

def improved_circle_fit(img):
    """改进的圆拟合算法，返回圆心坐标和半径"""
    # 预处理
    blurred = cv2.GaussianBlur(img, (9, 9), 2.0)
    
    # 1. 重心法获取粗略中心
    x_centroid, y_centroid = centroid_method(blurred, 0.3)
    
    if x_centroid is None:
        print("重心法未找到中心")
        return None, None, None
    
    # 2. 梯度计算
    h, w = img.shape
    sobel_x = cv2.Sobel(blurred, cv2.CV_64F, 1, 0, ksize=5)
    sobel_y = cv2.Sobel(blurred, cv2.CV_64F, 0, 1, ksize=5)
    magnitude = np.sqrt(sobel_x**2 + sobel_y**2)
    
    # 3. 边缘检测（用于半径计算）
    edges = cv2.Canny(blurred.astype(np.uint8), 50, 150)
    
    # 4. 梯度方向投票
    accum_size = 200
    accum = np.zeros((accum_size, accum_size), dtype=np.float32)
    edge_threshold = np.max(magnitude) * 0.3
    edge_points = np.where(magnitude > edge_threshold)
    
    if len(edge_points[0]) > 0:
        y_edges, x_edges = edge_points
        
        for i in range(len(y_edges)):
            x, y = x_edges[i], y_edges[i]
            dx, dy = sobel_x[y, x], sobel_y[y, x]
            norm = np.sqrt(dx**2 + dy**2)
            
            if norm > 0:
                for t in np.linspace(10, 100, 10):
                    cx = int(x - dx/norm * t)
                    cy = int(y - dy/norm * t)
                    
                    if 0 <= cx < w and 0 <= cy < h:
                        acc_x = int(cx * accum_size / w)
                        acc_y = int(cy * accum_size / h)
                        if 0 <= acc_x < accum_size and 0 <= acc_y < accum_size:
                            accum[acc_y, acc_x] += magnitude[y, x]
        
        # 找到投票峰值
        peak_y, peak_x = np.unravel_index(np.argmax(accum), accum.shape)
        x_hough = peak_x * w / accum_size
        y_hough = peak_y * h / accum_size
    else:
        x_hough, y_hough = x_centroid, y_centroid
    
    # 5. 高斯拟合获取精确中心
    x_final, y_final, gauss_params = gaussian_fit(img, (x_hough, y_hough))
    
    # 6. 计算半径（确保有效性）
    radius_estimate = None
    
    if gauss_params is not None:
        # 使用高斯参数估计半径（取sigma的平均值乘以2.5）
        sigma_x, sigma_y = gauss_params[3], gauss_params[4]
        if sigma_x > 0 and sigma_y > 0:
            radius_estimate = np.mean([sigma_x, sigma_y]) * 2.5
            # 确保半径在合理范围内
            radius_estimate = min(radius_estimate, min(h, w) // 2)
    
    if radius_estimate is None or radius_estimate <= 0:
        # 如果没有高斯参数或半径无效，使用距离边缘点的平均距离
        edge_pixels = np.column_stack(np.where(edges > 0))
        if len(edge_pixels) > 10:  # 至少有10个边缘点
            distances = np.sqrt((edge_pixels[:,1] - x_final)**2 + (edge_pixels[:,0] - y_final)**2)
            radius_estimate = np.median(distances)  # 使用中位数更稳定
        else:
            # 如果还是没有，使用保守估计
            radius_estimate = min(h, w) // 4  # 图像尺寸的1/4
    
    # 确保半径是正数且不太大
    radius_estimate = max(5, min(radius_estimate, min(h, w) // 2))
    
    return x_final, y_final, radius_estimate

def add_noise(img, noise_type="gaussian", noise_level=0.05):
    """向图像添加噪声"""
    noisy_img = img.copy().astype(np.float32)
    if noise_type == "gaussian":
        mean = 0
        stddev = noise_level * 255
        noise = np.random.normal(mean, stddev, img.shape)
        noisy_img += noise
    elif noise_type == "salt_pepper":
        prob = noise_level
        salt = np.random.rand(*img.shape) < prob / 2
        pepper = np.random.rand(*img.shape) < prob / 2
        noisy_img[salt] = 255
        noisy_img[pepper] = 0
    noisy_img = np.clip(noisy_img, 0, 255).astype(np.uint8)
    return noisy_img

def save_result_image(img, x_center, y_center, radius, filename):
    """保存结果图像，绘制圆心和圆"""
    result_img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    
    # 确保半径是有效的整数
    radius_int = int(round(radius))
    if radius_int <= 0:
        print(f"警告: 半径值异常 ({radius_int}), 使用默认值50")
        radius_int = 50
    
    # 确保圆心在图像范围内
    center_x = int(round(x_center))
    center_y = int(round(y_center))
    
    if center_x < 0 or center_x >= img.shape[1] or center_y < 0 or center_y >= img.shape[0]:
        print(f"警告: 圆心坐标超出图像范围 ({center_x}, {center_y})")
        # 调整到图像中心
        center_x = img.shape[1] // 2
        center_y = img.shape[0] // 2
    
    # 绘制拟合的圆
    cv2.circle(result_img, (center_x, center_y), radius_int, (0, 0, 255), 2)
    
    # 绘制圆心
    cv2.circle(result_img, (center_x, center_y), 6, (0, 255, 0), -1)
    
    # 绘制十字线
    cross_size = min(radius_int // 3, 25)
    cv2.line(result_img, (center_x-cross_size, center_y), 
             (center_x+cross_size, center_y), (255, 0, 0), 3)
    cv2.line(result_img, (center_x, center_y-cross_size), 
             (center_x, center_y+cross_size), (255, 0, 0), 3)
    
    # 添加坐标文本
    font = cv2.FONT_HERSHEY_SIMPLEX
    text_color = (255, 255, 255)
    bg_color = (0, 0, 0)
    
    # 创建文本背景
    text1 = f"Center: ({x_center:.1f}, {y_center:.1f})"
    text2 = f"Radius: {radius:.1f} px"
    
    # 获取文字尺寸
    (text1_width, text1_height), baseline1 = cv2.getTextSize(text1, font, 0.7, 2)
    (text2_width, text2_height), baseline2 = cv2.getTextSize(text2, font, 0.7, 2)
    
    max_width = max(text1_width, text2_width)
    total_height = text1_height + text2_height + 20
    
    # 绘制文字背景框
    cv2.rectangle(result_img, (5, 5), (max_width + 15, total_height), bg_color, -1)
    cv2.rectangle(result_img, (5, 5), (max_width + 15, total_height), (255, 255, 255), 1)
    
    # 绘制文字
    cv2.putText(result_img, text1, (10, 30), font, 0.7, text_color, 2)
    cv2.putText(result_img, text2, (10, 60), font, 0.7, text_color, 2)
    
    # 保存结果图像
    cv2.imwrite(filename, result_img)
    print(f"结果图像已保存为 {filename}")

# 创建结果文件夹
def create_result_folder(base_folder="output"):
    """创建一个带时间戳的结果文件夹"""
    if not os.path.exists(base_folder):
        os.makedirs(base_folder)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    result_folder = os.path.join(base_folder, f"run_{timestamp}")
    os.makedirs(result_folder)
    return result_folder

# 展示图片的函数
def show_image_with_title(image_path, title):
    img = cv2.imread(image_path)
    img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)  # 转换为 RGB 格式以便 Matplotlib 显示
    plt.imshow(img)
    plt.title(title)
    plt.axis('off')
    plt.show()

if __name__ == "__main__":
    image = cv2.imread(
        "D:\\POWER\\circle_center\\img\\img\\X0000_Y0000_C1_01.bmp",
        cv2.IMREAD_GRAYSCALE,
    )
    if image is None:
        print("图像加载失败，请检查路径是否正确！")
        raise SystemExit(1)

    print("=" * 50)
    print("改进算法 - 亚像素圆心提取")
    print("=" * 50)

    result_folder = create_result_folder()
    x_final, y_final, radius = improved_circle_fit(image)

    if x_final is not None:
        print(f"圆心坐标 (亚像素): ({x_final:.3f}, {y_final:.3f})")
        print(f"估计半径: {radius:.2f} 像素")
        with open(os.path.join(result_folder, "circle_center_result.txt"), "w") as f:
            f.write(f"圆心坐标: ({x_final:.3f}, {y_final:.3f})\n")
            f.write(f"估计半径: {radius:.2f} 像素\n")
            f.write(f"图像尺寸: {image.shape[1]}x{image.shape[0]}\n")
        save_result_image(
            image, x_final, y_final, radius,
            os.path.join(result_folder, "result_with_circle.jpg"),
        )
    else:
        print("未能检测到圆心")

    for i, noise_level in enumerate([0.05, 0.1, 0.2], start=1):
        noisy_image = add_noise(image, noise_type="gaussian", noise_level=noise_level)
        x_noisy, y_noisy, radius_noisy = improved_circle_fit(noisy_image)
        print(f"\n处理噪声图像 {i} (噪声强度: {noise_level})")
        if x_noisy is not None:
            print(f"圆心坐标 (亚像素): ({x_noisy:.3f}, {y_noisy:.3f})")
            print(f"估计半径: {radius_noisy:.2f} 像素")
            save_result_image(
                noisy_image, x_noisy, y_noisy, radius_noisy,
                os.path.join(result_folder, f"result_with_circle_noise_{i}.jpg"),
            )
        else:
            print("未能检测到圆心")

    show_image_with_title(
        os.path.join(result_folder, "result_with_circle.jpg"),
        "Original Image with Circle",
    )
    for i in range(1, 4):
        show_image_with_title(
            os.path.join(result_folder, f"result_with_circle_noise_{i}.jpg"),
            f"Noisy Image {i} with Circle",
        )