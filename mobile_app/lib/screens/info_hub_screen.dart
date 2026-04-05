import 'package:flutter/material.dart';
import '../theme.dart';

class InfoHubScreen extends StatelessWidget {
  const InfoHubScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text(
          'Information & Support',
          style: AppTextStyles.heading.copyWith(fontSize: 18),
        ),
        centerTitle: true,
      ),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          _infoCard(
            context,
            'Our Story',
            'Discover the journey of Le Maison Yelo Lane.',
            Icons.history_edu_rounded,
            const AboutUsPage(),
          ),
          const SizedBox(height: 12),
          _infoCard(
            context,
            'FAQs',
            'Find answers to frequently asked questions.',
            Icons.quiz_outlined,
            const FAQPage(),
          ),
          const SizedBox(height: 12),
          _infoCard(
            context,
            'Customer Service',
            'Contact us and see our operating hours.',
            Icons.headset_mic_outlined,
            const CustomerServicePage(),
          ),
          const SizedBox(height: 12),
          _infoCard(
            context,
            'Join Our Team',
            'See open positions and start your career with us.',
            Icons.work_outline_rounded,
            const CareersPage(),
          ),
          const SizedBox(height: 30),
          const Center(
            child: Text(
              'Le Maison Yelo Lane v1.0.0',
              style: TextStyle(color: Colors.grey, fontSize: 12),
            ),
          ),
        ],
      ),
    );
  }

  Widget _infoCard(BuildContext context, String title, String subtitle, IconData icon, Widget page) {
    return GestureDetector(
      onTap: () => Navigator.push(context, MaterialPageRoute(builder: (_) => page)),
      child: Container(
        padding: const EdgeInsets.all(18),
        decoration: BoxDecoration(
          color: Colors.white,
          borderRadius: BorderRadius.circular(16),
          boxShadow: [
            BoxShadow(
              color: Colors.black.withOpacity(0.04),
              blurRadius: 10,
              offset: const Offset(0, 4),
            ),
          ],
        ),
        child: Row(
          children: [
            Container(
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: AppColors.primary.withOpacity(0.08),
                borderRadius: BorderRadius.circular(12),
              ),
              child: Icon(icon, color: AppColors.primary, size: 24),
            ),
            const SizedBox(width: 16),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    title,
                    style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 16),
                  ),
                  const SizedBox(height: 4),
                  Text(
                    subtitle,
                    style: AppTextStyles.muted.copyWith(fontSize: 12),
                  ),
                ],
              ),
            ),
            const Icon(Icons.chevron_right_rounded, color: Colors.grey),
          ],
        ),
      ),
    );
  }
}

// ── OUR STORY PAGE ──────────────────────────────────────────────────
class AboutUsPage extends StatelessWidget {
  const AboutUsPage({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Our Story')),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(24),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text(
              'Welcome to Our Journey',
              style: TextStyle(
                fontSize: 24,
                fontWeight: FontWeight.w900,
                color: AppColors.primary,
                fontFamily: 'Playfair Display',
              ),
            ),
            const SizedBox(height: 20),
            const Text(
              'Welcome to the Le Maison Yelo Lane updates page! Here we share everything from our humble beginnings to the latest seasonal menu additions.',
              style: TextStyle(fontSize: 16, height: 1.6, color: AppColors.textMain),
            ),
            const SizedBox(height: 24),
            Container(
              padding: const EdgeInsets.all(20),
              decoration: BoxDecoration(
                color: AppColors.primary.withOpacity(0.04),
                borderRadius: BorderRadius.circular(16),
                border: const Border(left: BorderSide(color: AppColors.primary, width: 4)),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    'Our Latest Expansion',
                    style: AppTextStyles.heading.copyWith(fontSize: 18),
                  ),
                  const SizedBox(height: 8),
                  const Text(
                    'We recently opened our doors to a completely revamped dining space, designed to bring you the coziest cafe experience possible. Thank you to everyone who joined our reopening week!',
                    style: TextStyle(fontSize: 14, height: 1.5),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 24),
            const Text(
              'Stay tuned for more updates as we continue introducing new dessert creations and specialty coffee blends tailored just for you.',
              style: TextStyle(fontSize: 16, height: 1.6),
            ),
          ],
        ),
      ),
    );
  }
}

// ── FAQ PAGE ──────────────────────────────────────────────────
class FAQPage extends StatelessWidget {
  const FAQPage({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Frequently Asked Questions')),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          _faqTile('Do you have vegetarian options?', 'Yes, we have several vegetarian dishes available on our main menu.'),
          _faqTile('What are your delivery areas?', 'We currently deliver entirely to Santa Cruz, Magdalena, Los Baños, and Cavinti Laguna areas.'),
          _faqTile('How do reservations work?', 'You can book tables or our Exclusive Venue at least 1 day in advance through the portal. Admin approval is required for all bookings.'),
        ],
      ),
    );
  }

  Widget _faqTile(String question, String answer) {
    return Container(
      margin: const EdgeInsets.only(bottom: 12),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(12),
        boxShadow: [BoxShadow(color: Colors.black.withOpacity(0.03), blurRadius: 8)],
      ),
      child: ExpansionTile(
        title: Text(question, style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 14)),
        leading: const Icon(Icons.question_answer_outlined, color: AppColors.primary, size: 20),
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
            child: Text(answer, style: const TextStyle(color: Colors.grey, height: 1.5)),
          ),
        ],
      ),
    );
  }
}

// ── CUSTOMER SERVICE PAGE ──────────────────────────────────────────────────
class CustomerServicePage extends StatelessWidget {
  const CustomerServicePage({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Customer Service')),
      body: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text(
              'Your satisfaction is our top priority. We are completely committed to ensuring that every order meets your expectations.',
              style: TextStyle(fontSize: 16, height: 1.5),
            ),
            const SizedBox(height: 30),
            _contactCard(Icons.headset_mic_rounded, 'Contact Us', '+63 912 345 6789\nsupport@lemaisonyelo.com'),
            const SizedBox(height: 16),
            _contactCard(Icons.access_time_rounded, 'Operating Hours', 'Mon - Sun: 11:30 AM - 8:30 PM'),
          ],
        ),
      ),
    );
  }

  Widget _contactCard(IconData icon, String title, String info) {
    return Container(
      padding: const EdgeInsets.all(20),
      width: double.infinity,
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: Colors.grey.withOpacity(0.1)),
      ),
      child: Column(
        children: [
          Icon(icon, color: AppColors.primary, size: 30),
          const SizedBox(height: 12),
          Text(title, style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 16)),
          const SizedBox(height: 6),
          Text(info, textAlign: TextAlign.center, style: const TextStyle(color: Colors.grey, fontSize: 14)),
        ],
      ),
    );
  }
}

// ── CAREERS PAGE ──────────────────────────────────────────────────
class CareersPage extends StatelessWidget {
  const CareersPage({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Join Our Team')),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(24),
        child: Column(
          children: [
            const Text(
              'Le Maison Yelo Lane isn’t just a cafe; it’s a family of passionate food lovers and coffee enthusiasts.',
              textAlign: TextAlign.center,
              style: TextStyle(fontSize: 16, height: 1.5),
            ),
            const SizedBox(height: 30),
            _jobTile('Barista', 'Full-time / Part-time'),
            _jobTile('Delivery Rider', 'Freelance'),
            const SizedBox(height: 20),
            const Text('Send your resume to\ncareers@lemaisonyelo.com', textAlign: TextAlign.center, style: TextStyle(fontWeight: FontWeight.bold, color: AppColors.primary)),
          ],
        ),
      ),
    );
  }

  Widget _jobTile(String title, String type) {
    return Container(
      margin: const EdgeInsets.only(bottom: 12),
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: Colors.grey.withOpacity(0.1)),
      ),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(title, style: const TextStyle(fontWeight: FontWeight.bold)),
              Text(type, style: const TextStyle(color: Colors.grey, fontSize: 12)),
            ],
          ),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
            decoration: BoxDecoration(
              color: AppColors.primary,
              borderRadius: BorderRadius.circular(20),
            ),
            child: const Text('Apply', style: TextStyle(color: Colors.white, fontSize: 12, fontWeight: FontWeight.bold)),
          ),
        ],
      ),
    );
  }
}
