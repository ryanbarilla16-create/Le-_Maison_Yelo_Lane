from PIL import Image, ImageDraw

def create_rider_icon():
    # Colors matching the system theme
    coffee_brown = (109, 76, 65)  # #6D4C41
    vibrant_yellow = (249, 168, 37) # #F9A825
    
    size = 1024
    img = Image.new('RGB', (size, size), coffee_brown)
    draw = ImageDraw.Draw(img)
    
    # Draw a stylized motorcycle (simplified)
    # This is a rough silhouette for a clean look
    margin = 200
    
    # Body/Chassis
    draw.ellipse([margin, size//2, size-margin, size-margin], fill=vibrant_yellow)
    
    # Wheels
    wheel_size = 150
    draw.ellipse([margin, size-margin-wheel_size, margin+wheel_size, size-margin], fill=(40, 40, 40))
    draw.ellipse([size-margin-wheel_size, size-margin-wheel_size, size-margin, size-margin], fill=(40, 40, 40))
    
    # Delivery Box
    draw.rectangle([size//2, margin, size-margin-100, size//2+100], fill=vibrant_yellow)
    
    # Arched Window Logo inside the box (Le Maison brand)
    # Simple arch
    draw.chord([size//2+50, margin+20, size-margin-150, margin+150], 180, 360, outline=coffee_brown, width=10)
    
    img.save('rider_logo_generated.png')
    print("Logo generated successfully as rider_logo_generated.png")

if __name__ == "__main__":
    create_rider_icon()
