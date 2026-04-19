import 'package:flutter/material.dart';
import '../theme.dart';
import 'login_screen.dart';

class WelcomeScreen extends StatefulWidget {
  const WelcomeScreen({super.key});

  @override
  State<WelcomeScreen> createState() => _WelcomeScreenState();
}

class _WelcomeScreenState extends State<WelcomeScreen> with TickerProviderStateMixin {
  late AnimationController _mainController;
  late Animation<double> _logoFade;
  late Animation<Offset> _logoSlide;
  late Animation<double> _textFade;
  late Animation<Offset> _textSlide;
  late Animation<double> _buttonFade;
  late Animation<Offset> _buttonSlide;
  
  late AnimationController _pulseController;
  late AnimationController _driftController;
  late AnimationController _shimmerController;

  bool _isEntering = false;
  double _loadingProgress = 0.0;

  @override
  void initState() {
    super.initState();

    _mainController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 2500),
    );

    _logoFade = Tween<double>(begin: 0, end: 1).animate(
      CurvedAnimation(parent: _mainController, curve: const Interval(0.0, 0.4, curve: Curves.easeOut)),
    );
    _logoSlide = Tween<Offset>(begin: const Offset(0, -0.3), end: Offset.zero).animate(
      CurvedAnimation(parent: _mainController, curve: const Interval(0.0, 0.4, curve: Curves.easeOutBack)),
    );

    _textFade = Tween<double>(begin: 0, end: 1).animate(
      CurvedAnimation(parent: _mainController, curve: const Interval(0.3, 0.7, curve: Curves.easeOut)),
    );
    _textSlide = Tween<Offset>(begin: const Offset(0, 0.2), end: Offset.zero).animate(
      CurvedAnimation(parent: _mainController, curve: const Interval(0.3, 0.7, curve: Curves.easeOutCubic)),
    );

    _buttonFade = Tween<double>(begin: 0, end: 1).animate(
      CurvedAnimation(parent: _mainController, curve: const Interval(0.6, 1.0, curve: Curves.easeOut)),
    );
    _buttonSlide = Tween<Offset>(begin: const Offset(0, 0.4), end: Offset.zero).animate(
      CurvedAnimation(parent: _mainController, curve: const Interval(0.6, 1.0, curve: Curves.elasticOut)),
    );

    _pulseController = AnimationController(
      vsync: this,
      duration: const Duration(seconds: 2),
    )..repeat(reverse: true);

    _driftController = AnimationController(
      vsync: this,
      duration: const Duration(seconds: 60),
    )..repeat();

    _shimmerController = AnimationController(
      vsync: this,
      duration: const Duration(seconds: 3),
    )..repeat();

    _mainController.forward();
  }

  @override
  void dispose() {
    _mainController.dispose();
    _pulseController.dispose();
    _driftController.dispose();
    _shimmerController.dispose();
    super.dispose();
  }

  Future<void> _handleGetStarted() async {
    if (_isEntering) return;
    
    setState(() {
      _isEntering = true;
      _loadingProgress = 0.0;
    });

    for (int i = 1; i <= 100; i++) {
      await Future.delayed(const Duration(milliseconds: 15));
      if (!mounted) return;
      setState(() {
        _loadingProgress = i / 100;
      });
    }

    if (!mounted) return;
    
    Navigator.push(
      context,
      PageRouteBuilder(
        transitionDuration: const Duration(milliseconds: 1000),
        pageBuilder: (context, animation, secondaryAnimation) => const LoginScreen(),
        transitionsBuilder: (context, animation, secondaryAnimation, child) {
          return FadeTransition(opacity: animation, child: child);
        },
      ),
    ).then((_) {
      if (mounted) {
        setState(() {
          _isEntering = false;
          _loadingProgress = 0.0;
        });
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Container(
        width: double.infinity,
        height: double.infinity,
        decoration: const BoxDecoration(color: Colors.white),
        child: Stack(
          children: [
            _buildParallaxBg(),
            Positioned(
              top: 0,
              left: 0,
              right: 0,
              child: CustomPaint(
                size: Size(MediaQuery.of(context).size.width, 420),
                painter: _WavePainter(),
              ),
            ),
            SafeArea(
              child: Column(
                children: [
                  const Spacer(flex: 3),
                  FadeTransition(
                    opacity: _logoFade,
                    child: SlideTransition(
                      position: _logoSlide,
                      child: Column(
                        children: [
                          Container(
                            width: 140,
                            height: 140,
                            padding: const EdgeInsets.all(5),
                            decoration: BoxDecoration(
                              color: Colors.white,
                              shape: BoxShape.circle,
                              boxShadow: [
                                BoxShadow(
                                  color: AppColors.primary.withOpacity(0.25),
                                  blurRadius: 40,
                                  spreadRadius: 10,
                                ),
                              ],
                            ),
                            child: ClipOval(
                              child: Image.asset(
                                'brand/logo.jpg',
                                fit: BoxFit.cover,
                              ),
                            ),
                          ),
                          const SizedBox(height: 24),
                          const Text(
                            'LE MAISON',
                            style: TextStyle(
                              fontSize: 48,
                              fontWeight: FontWeight.w900,
                              color: Colors.white,
                              letterSpacing: 2,
                              height: 1,
                              shadows: [Shadow(color: Colors.black26, blurRadius: 10, offset: Offset(0, 4))],
                            ),
                          ),
                          const Text(
                            'YELO LANE',
                            style: TextStyle(
                              fontSize: 18,
                              color: Colors.white70,
                              fontWeight: FontWeight.bold,
                              letterSpacing: 10,
                            ),
                          ),
                        ],
                      ),
                    ),
                  ),
                  const Spacer(flex: 3),
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 40),
                    child: Column(
                      children: [
                        FadeTransition(
                          opacity: _textFade,
                          child: SlideTransition(
                            position: _textSlide,
                            child: Column(
                              children: [
                                const Text(
                                  'Hungry? Get It Fast',
                                  style: TextStyle(
                                    fontSize: 34,
                                    fontWeight: FontWeight.w900,
                                    color: AppColors.textMain,
                                    height: 1.2,
                                  ),
                                ),
                                const SizedBox(height: 15),
                                Text(
                                  'Savor the flavor of artisanal cuisine delivered right to your doorstep with love and speed.',
                                  textAlign: TextAlign.center,
                                  style: TextStyle(
                                    fontSize: 16,
                                    color: AppColors.textMuted.withOpacity(0.8),
                                    height: 1.6,
                                    fontWeight: FontWeight.w500,
                                  ),
                                ),
                              ],
                            ),
                          ),
                        ),
                        const SizedBox(height: 50),
                        FadeTransition(
                          opacity: _buttonFade,
                          child: SlideTransition(
                            position: _buttonSlide,
                            child: _isEntering ? _buildLoadingBar() : _buildActionBtn(),
                          ),
                        ),
                      ],
                    ),
                  ),
                  const Spacer(flex: 1),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildLoadingBar() {
     return Column(
       children: [
         Container(
           width: double.infinity,
           height: 12,
           decoration: BoxDecoration(
             color: AppColors.primary.withOpacity(0.1),
             borderRadius: BorderRadius.circular(10),
           ),
           child: Stack(
             children: [
               AnimatedContainer(
                 duration: const Duration(milliseconds: 200),
                 width: MediaQuery.of(context).size.width * 0.8 * _loadingProgress,
                 decoration: BoxDecoration(
                   gradient: const LinearGradient(
                     colors: [AppColors.primary, AppColors.primaryLight],
                   ),
                   borderRadius: BorderRadius.circular(10),
                   boxShadow: [
                     BoxShadow(
                       color: AppColors.primary.withOpacity(0.3),
                       blurRadius: 8,
                       offset: const Offset(0, 4),
                     ),
                   ],
                 ),
               ),
             ],
           ),
         ),
         const SizedBox(height: 12),
         const Text(
           'PREPARING YOUR EXPERIENCE...',
           style: TextStyle(
             fontSize: 10,
             fontWeight: FontWeight.w900,
             color: AppColors.primary,
             letterSpacing: 2,
           ),
         ),
       ],
     );
  }

  Widget _buildParallaxBg() {
    return AnimatedBuilder(
      animation: _driftController,
      builder: (context, child) {
        return Stack(
          children: List.generate(20, (index) {
            double left = (index * 73.0) % MediaQuery.of(context).size.width;
            double top = (index * 117.0) % MediaQuery.of(context).size.height;
            double drift = _driftController.value * 2 * 3.14159;
            double xShift = 30 * (index % 2 == 0 ? 1 : -1) * (1 + (index % 3));
            double yShift = 40 * (index % 2 != 0 ? 1 : -1) * (1 + (index % 2));

            return Positioned(
              left: left + xShift * _driftController.value,
              top: top + yShift * _driftController.value,
              child: Opacity(
                opacity: 0.04,
                child: Transform.rotate(
                  angle: drift * 0.1,
                  child: Icon(
                    [Icons.local_pizza, Icons.coffee, Icons.icecream, Icons.fastfood, Icons.ramen_dining][index % 5],
                    size: 40 + (index % 5) * 12.0,
                    color: AppColors.primary,
                  ),
                ),
              ),
            );
          }),
        );
      },
    );
  }

  Widget _buildActionBtn() {
    return ScaleTransition(
      scale: Tween<double>(begin: 1.0, end: 1.04).animate(
        CurvedAnimation(parent: _pulseController, curve: Curves.easeInOut),
      ),
      child: GestureDetector(
        onTap: _handleGetStarted,
        child: Container(
          width: double.infinity,
          height: 75,
          decoration: BoxDecoration(
            color: Colors.white,
            borderRadius: BorderRadius.circular(40),
            boxShadow: [
              BoxShadow(
                color: AppColors.primary.withOpacity(0.2),
                blurRadius: 30,
                offset: const Offset(0, 15),
              ),
            ],
          ),
          child: ClipRRect(
            borderRadius: BorderRadius.circular(40),
            child: Stack(
              children: [
                AnimatedBuilder(
                  animation: _shimmerController,
                  builder: (context, child) {
                    return Positioned(
                      left: -200 + (MediaQuery.of(context).size.width * 2 * _shimmerController.value),
                      top: 0,
                      bottom: 0,
                      child: Container(
                        width: 150,
                        decoration: BoxDecoration(
                          gradient: LinearGradient(
                            colors: [
                              Colors.white.withOpacity(0),
                              Colors.white.withOpacity(0.4),
                              Colors.white.withOpacity(0),
                            ],
                            begin: Alignment.topLeft,
                            end: Alignment.bottomRight,
                          ),
                        ),
                      ),
                    );
                  },
                ),
                Row(
                  children: [
                    const SizedBox(width: 10),
                    Container(
                      width: 55,
                      height: 55,
                      decoration: const BoxDecoration(
                        color: AppColors.primary,
                        shape: BoxShape.circle,
                      ),
                      child: const Icon(Icons.keyboard_arrow_right_rounded, color: Colors.white, size: 36),
                    ),
                    const Expanded(
                      child: Center(
                        child: Text(
                          'GET STARTED',
                          style: TextStyle(
                            fontSize: 19,
                            fontWeight: FontWeight.w900,
                            color: AppColors.textMain,
                            letterSpacing: 3,
                          ),
                        ),
                      ),
                    ),
                    const SizedBox(width: 65),
                  ],
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _WavePainter extends CustomPainter {
  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()..color = AppColors.primary..style = PaintingStyle.fill;
    final path = Path();
    path.lineTo(0, size.height - 80);
    path.quadraticBezierTo(size.width * 0.25, size.height, size.width * 0.5, size.height - 40);
    path.quadraticBezierTo(size.width * 0.75, size.height - 80, size.width, size.height);
    path.lineTo(size.width, 0);
    path.close();
    canvas.drawShadow(path, Colors.black, 10, true);
    canvas.drawPath(path, paint);
  }
  @override bool shouldRepaint(covariant CustomPainter oldDelegate) => false;
}
