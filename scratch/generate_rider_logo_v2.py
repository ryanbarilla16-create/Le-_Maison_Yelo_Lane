from PIL import Image, ImageDraw, ImageFont

def create_elegant_rider_icon():
    # Colors
    coffee_brown = (62, 39, 35)    # #3E2723 (Deep Mocha)
    gold = (212, 175, 55)           # #D4AF37 (Metallic Gold)
    cream = (253, 251, 249)         # #FDFBF9 (Latte Cream)
    
    size = 1024
    img = Image.new('RGB', (size, size), coffee_brown)
    draw = ImageDraw.Draw(img)
    
    # Draw a gold border
    border_width = 40
    draw.rectangle([border_width, border_width, size-border_width, size-border_width], outline=gold, width=20)
    
    # Arched Window (Brand Identity)
    # Using multiple arcs for a "premium" feel
    center_x, center_y = size // 2, size // 2 - 100
    w, h = 400, 500
    
    # Main Arch
    draw.chord([center_x - w//2, center_y - h//2, center_x + w//2, center_y + h//2], 180, 360, outline=cream, width=15)
    draw.rectangle([center_x - w//2, center_y, center_x + w//2, center_y + h//2], outline=cream, width=15)
    
    # Internal Grid (Elegant lines)
    draw.line([center_x, center_y - h//2, center_x, center_y + h//2], fill=cream, width=8)
    draw.line([center_x - w//2, center_y - 50, center_x + w//2, center_y - 50], fill=cream, width=8)
    
    # "RIDER" Banner at the bottom
    banner_h = 180
    draw.rectangle([100, size - 300, size - 100, size - 120], fill=gold)
    
    # Note: Fonts might not be available, so we'll draw a stylized 'R' or just the shape
    # Try to draw "RIDER" using shapes
    text_y = size - 260
    # Stylized R-I-D-E-R (Simplified shapes)
    draw.text((center_x - 100, text_y), "RIDER", fill=coffee_brown) 
    # Since text() needs a font object, we'll just skip text and use a clean ribbon.
    
    img.save('rider_logo_elegant.png')
    print("Elegant logo generated successfully")

if __name__ == "__main__":
    create_elegant_rider_icon()
