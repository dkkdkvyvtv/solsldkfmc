class VapeShop {
    constructor() {
        this.user = null;
        this.balance = 0;
        this.userBalance = 0;
        this.isVerified = false;
        this.isAddingToCart = false;
        this.cart = {
            items: [],
            total: 0
        };
        this.deliveryType = 'pickup';
        this.selectedCity = null;
        this.selectedPickupLocation = null;
        this.deliveryPrice = 0;
        this.currentOrderStep = 'customer';
        this.init();
    }

    async init() {
        await this.initTelegramWebApp();
        this.setupEventListeners();
        this.highlightActiveNav();
        
        if (window.location.pathname === '/cart') {
            await this.loadCart();
        }
        
        if (window.location.pathname === '/profile') {
            await this.loadProfile();
        }
        
        if (window.location.pathname === '/') {
            this.updateMiniProfile();
        }
    }

    async initTelegramWebApp() {
        try {
            if (typeof window.Telegram !== 'undefined' && window.Telegram.WebApp) {
                console.log('Telegram Web App доступен');
                const tg = window.Telegram.WebApp;
                
                tg.ready();
                tg.expand();
                
                const tgUser = tg.initDataUnsafe?.user;
                
                if (tgUser) {
                    console.log('Данные пользователя Telegram получены');
                    
                    this.user = {
                        id: tgUser.id,
                        first_name: tgUser.first_name || 'Пользователь',
                        username: tgUser.username || `user_${tgUser.id}`,
                        photo_url: tgUser.photo_url || '/static/images/default-avatar.png'
                    };
                    
                    await this.initWithTelegram(tg.initData);
                    
                    this.setupTelegramMainButton(tg);
                    
                } else {
                    console.log('Данные пользователя Telegram не получены');
                    await this.initFallback();
                }
                
            } else {
                console.log('Не в Telegram Web App, используем браузерный режим');
                await this.initFallback();
            }
            
            this.updateMiniProfile();
            
        } catch (error) {
            console.error('Ошибка инициализации Telegram Web App:', error);
            await this.initFallback();
        }
    }

    async initWithTelegram(initData) {
        try {
            const response = await fetch('/api/init', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    initData: initData,
                    user: this.user
                })
            });
            
            const data = await response.json();
            this.balance = data.balance || 0;
            this.userBalance = data.balance || 0;
            this.isVerified = data.is_verified || false;
            
        } catch (error) {
            console.error('Ошибка инициализации с Telegram:', error);
        }
    }

    setupTelegramMainButton(tg) {
        if (!tg || !tg.MainButton) return;
        
        // УБРАН ТЕКСТ "Открыть каталог" для мини-приложения
        tg.MainButton.hide();
        
        tg.setBackgroundColor('#0f0f0f');
    }

    async initFallback() {
        try {
            const response = await fetch('/api/init', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({})
            });
            
            const data = await response.json();
            this.user = data.user;
            this.balance = data.balance || 0;
            this.userBalance = data.balance || 0;
            this.isVerified = data.is_verified || false;
            
        } catch (error) {
            console.error('Ошибка fallback инициализации:', error);
            this.user = {
                id: 1,
                first_name: 'Тестовый Пользователь',
                username: 'test_user',
                photo_url: '/static/images/default-avatar.png'
            };
            this.balance = 1500;
            this.userBalance = 1500;
            this.isVerified = false;
        }
    }

    highlightActiveNav() {
        const currentPath = window.location.pathname;
        const navItems = document.querySelectorAll('.nav-item');
        
        navItems.forEach(item => {
            item.classList.remove('active');
            const href = item.getAttribute('href');
            
            if (href === currentPath || (href === '/' && currentPath === '/')) {
                item.classList.add('active');
            }
        });
    }

    updateMiniProfile() {
        if (window.location.pathname === '/' || window.location.pathname === '/product/') {
            const avatar = document.getElementById('user-avatar');
            const username = document.getElementById('username');
            const balance = document.getElementById('balance');
            
            if (avatar && this.user) {
                avatar.src = this.user.photo_url || '/static/images/default-avatar.png';
                avatar.onerror = function() {
                    this.src = '/static/images/default-avatar.png';
                };
            }
            if (username && this.user) username.textContent = this.user.first_name || 'Пользователь';
            if (balance) balance.textContent = `${this.balance} руб.`;
        }
        
        if (window.location.pathname === '/profile') {
            this.updateProfilePage();
        }
    }

    updateProfilePage() {
        const avatar = document.getElementById('profile-avatar');
        const username = document.getElementById('profile-username');
        const mainBalance = document.getElementById('main-balance');
        
        if (avatar && this.user) {
            avatar.src = this.user.photo_url || '/static/images/default-avatar.png';
            avatar.onerror = function() {
                this.src = '/static/images/default-avatar.png';
            };
        }
        if (username && this.user) username.textContent = this.user.first_name || 'Пользователь';
        if (mainBalance) mainBalance.textContent = `${this.balance} руб.`;
    }

    setupEventListeners() {
        const addToCartButtons = document.querySelectorAll('.add-to-cart-btn');
        addToCartButtons.forEach(button => {
            button.addEventListener('click', (e) => {
                e.stopPropagation();
                const productId = button.getAttribute('data-product-id');
                if (productId) {
                    this.addToCart(parseInt(productId));
                }
            });
        });
    }

    async addToCart(productId) {
        if (this.isAddingToCart) {
            return;
        }
        
        this.isAddingToCart = true;
        
        try {
            const response = await fetch('/api/cart/add', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    product_id: productId
                })
            });
            
            const result = await response.json();
            
            if (result.success) {
                this.showNotification('Товар добавлен в корзину');
                if (window.location.pathname === '/cart') {
                    await this.loadCart();
                }
            } else {
                this.showNotification(result.error || 'Ошибка при добавлении в корзину', 'error');
            }
        } catch (error) {
            console.error('Ошибка:', error);
            this.showNotification('Ошибка при добавлении в корзину', 'error');
        } finally {
            this.isAddingToCart = false;
        }
    }

    async loadCart() {
        try {
            const response = await fetch('/api/cart/items');
            const data = await response.json();
            this.cart = data;
            this.renderCart();
        } catch (error) {
            console.error('Ошибка загрузки корзины:', error);
            const cartItems = document.getElementById('cart-items');
            if (cartItems) {
                cartItems.innerHTML = '<div class="error">Ошибка загрузки корзины</div>';
            }
        }
    }

    renderCart() {
        if (typeof window.renderCartItems === 'function') {
            window.renderCartItems(this.cart);
        } else {
            const cartItems = document.getElementById('cart-items');
            const cartTotalSection = document.getElementById('cart-total-section');
            const emptyCart = document.getElementById('empty-cart');
            const balancePaymentSection = document.getElementById('balance-payment-section');
            const availableBalance = document.getElementById('available-balance');
            
            if (!this.cart.items || this.cart.items.length === 0) {
                if (cartItems) cartItems.style.display = 'none';
                if (cartTotalSection) cartTotalSection.style.display = 'none';
                if (balancePaymentSection) balancePaymentSection.style.display = 'none';
                if (emptyCart) emptyCart.style.display = 'block';
                return;
            }
            
            if (emptyCart) emptyCart.style.display = 'none';
            if (cartTotalSection) cartTotalSection.style.display = 'block';
            
            if (balancePaymentSection) {
                balancePaymentSection.style.display = 'block';
                this.loadUserBalance();
            }
            
            if (cartItems) {
                cartItems.style.display = 'block';
                cartItems.innerHTML = this.cart.items.map(item => `
                    <div class="cart-item">
                        <div class="cart-item-image">
                            <img src="${item.image}" alt="${item.name}" onerror="this.src='/static/images/default-product.png'">
                        </div>
                        <div class="cart-item-info">
                            <h4>${item.name}</h4>
                            <div class="item-price">${item.price || 0} руб. × ${item.quantity || 1}</div>
                            <div class="quantity-controls">
                                <button class="quantity-btn" onclick="updateQuantity(${item.id}, ${(item.quantity || 1) - 1})">-</button>
                                <span>${item.quantity || 1}</span>
                                <button class="quantity-btn" onclick="updateQuantity(${item.id}, ${(item.quantity || 1) + 1})">+</button>
                            </div>
                        </div>
                        <div class="item-total">${(item.total || 0)} руб.</div>
                    </div>
                `).join('');
            }
            
            if (document.getElementById('cart-total')) {
                document.getElementById('cart-total').textContent = (this.cart.total || 0) + ' руб.';
            }
            if (document.getElementById('cashback-amount')) {
                this.updateLoyaltyCashback(this.cart.total);
            }
            
            if (availableBalance && this.userBalance !== undefined) {
                availableBalance.textContent = this.userBalance + ' руб.';
            }
            
            this.updateBalancePayment();
        }
    }

    async updateQuantity(productId, newQuantity) {
        if (newQuantity < 1) {
            await this.removeFromCart(productId);
            return;
        }
        
        try {
            const response = await fetch('/api/cart/update', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    product_id: productId,
                    quantity: newQuantity
                })
            });
            
            const result = await response.json();
            if (result.success) {
                await this.loadCart();
                this.updateOrderSummary();
            }
        } catch (error) {
            console.error('Ошибка обновления количества:', error);
            this.showNotification('Ошибка обновления количества', 'error');
        }
    }

    async removeFromCart(productId) {
        try {
            const response = await fetch('/api/cart/remove', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    product_id: productId
                })
            });
            
            const result = await response.json();
            if (result.success) {
                await this.loadCart();
                this.updateOrderSummary();
            }
        } catch (error) {
            console.error('Ошибка удаления из корзины:', error);
            this.showNotification('Ошибка удаления из корзины', 'error');
        }
    }

    async loadProfile() {
        try {
            const response = await fetch('/api/user/profile');
            const data = await response.json();
            this.renderProfile(data);
        } catch (error) {
            console.error('Ошибка загрузки профиля:', error);
        }
    }

    renderProfile(data) {
        this.balance = data.balance || 0;
        this.userBalance = data.balance || 0;
        this.isVerified = data.is_verified || false;
        this.updateProfilePage();
        
        this.renderOrders(data.orders || []);
    }

    renderOrders(orders) {
        const ordersList = document.getElementById('orders-list');
        if (!ordersList) return;
        
        if (orders.length === 0) {
            ordersList.innerHTML = `
                <div class="empty-orders">
                    <div class="empty-icon">📦</div>
                    <h4>Заказов пока нет</h4>
                    <p>Сделайте свой первый заказ!</p>
                </div>
            `;
            return;
        }
        
        ordersList.innerHTML = orders.map(order => {
            let statusText = '';
            let statusClass = '';
            
            switch(order.status) {
                case 'completed':
                    statusText = 'Выполнен';
                    statusClass = 'status-completed';
                    break;
                case 'pending':
                    statusText = 'В обработке';
                    statusClass = 'status-pending';
                    break;
                case 'cancelled':
                    statusText = 'Отменен';
                    statusClass = 'status-cancelled';
                    break;
                default:
                    statusText = order.status;
                    statusClass = 'status-pending';
            }
            
            const orderDate = new Date(order.created_at);
            const formattedDate = orderDate.toLocaleDateString('ru-RU', {
                day: '2-digit',
                month: '2-digit',
                year: 'numeric',
                hour: '2-digit',
                minute: '2-digit'
            });
            
            let deliveryInfo = '';
            if (order.delivery_type === 'pickup') {
                deliveryInfo = order.pickup_location || 'Пункт выдачи не указан';
            } else {
                deliveryInfo = order.delivery_city ? `Доставка в ${order.delivery_city}` : 'Доставка';
            }
            
            return `
                <div class="order-item">
                    <div class="order-header">
                        <div class="order-id">Заказ #${order.id}</div>
                        <div class="order-date">${formattedDate}</div>
                    </div>
                    <div class="order-details">
                        <div>
                            <span>Сумма:</span>
                            <span>${order.total_amount} руб.</span>
                        </div>
                        <div>
                            <span>Кешбек:</span>
                            <span>+${order.cashback_earned} руб.</span>
                        </div>
                        <div>
                            <span>Получение:</span>
                            <span>${deliveryInfo}</span>
                        </div>
                        <div>
                            <span>Статус:</span>
                            <span class="order-status ${statusClass}">${statusText}</span>
                        </div>
                    </div>
                </div>
            `;
        }).join('');
    }

    async checkVerification() {
        try {
            const response = await fetch('/api/user/profile');
            const data = await response.json();
            this.isVerified = data.is_verified || false;
            return this.isVerified;
        } catch (error) {
            console.error('Ошибка проверки верификации:', error);
            return false;
        }
    }

    async openOrderModal() {
        const modal = document.getElementById('order-modal');
        if (modal) {
            modal.style.display = 'flex';
            
            this.deliveryType = 'pickup';
            this.selectedCity = null;
            this.selectedPickupLocation = null;
            this.deliveryPrice = 0;
            this.currentOrderStep = 'customer';
            
            this.showOrderStep('customer');
            
            await this.loadCities();
            
            this.updateOrderSummary();
            
            this.updateVerificationWarning();
        }
    }

    async updateVerificationWarning() {
        const isVerified = await this.checkVerification();
        
        if (typeof window.updateVerificationWarning === 'function') {
            window.updateVerificationWarning(isVerified);
        } else {
            const verificationWarning = document.getElementById('verification-warning');
            const submitOrderBtn = document.getElementById('submit-order-btn');
            
            if (verificationWarning) {
                verificationWarning.style.display = isVerified ? 'none' : 'flex';
            }
            
            if (submitOrderBtn) {
                submitOrderBtn.disabled = !isVerified;
                submitOrderBtn.textContent = isVerified ? 'Подтвердить заказ' : 'Верификация требуется';
            }
        }
    }

    async loadCities() {
        try {
            const response = await fetch('/api/cities');
            const cities = await response.json();
            
            if (typeof window.renderCities === 'function') {
                window.renderCities(cities);
            } else {
                const citySelector = document.getElementById('city-selector');
                if (citySelector) {
                    if (cities.length === 0) {
                        citySelector.innerHTML = '<div class="loading-cities">Нет доступных городов</div>';
                        return;
                    }
                    
                    citySelector.innerHTML = cities.map(city => `
                        <button type="button" class="city-btn" onclick="vapeShop.selectCity('${city}')">
                            ${city}
                        </button>
                    `).join('');
                }
            }
        } catch (error) {
            console.error('Ошибка загрузки городов:', error);
        }
    }

    async loadPickupLocations() {
        if (!this.selectedCity) return;
        
        try {
            const response = await fetch(`/api/pickup-locations?type=pickup&city=${encodeURIComponent(this.selectedCity)}`);
            const locations = await response.json();
            
            if (typeof window.renderPickupLocations === 'function') {
                window.renderPickupLocations(locations);
            } else {
                const pickupLocationSelect = document.getElementById('pickup-location');
                if (pickupLocationSelect) {
                    pickupLocationSelect.innerHTML = '<option value="">Выберите пункт выдачи</option>';
                    
                    if (locations.length === 0) {
                        pickupLocationSelect.innerHTML += '<option value="" disabled>Нет доступных пунктов</option>';
                        pickupLocationSelect.disabled = true;
                    } else {
                        locations.forEach(loc => {
                            pickupLocationSelect.innerHTML += `<option value="${loc.id}">${loc.name} - ${loc.address}</option>`;
                        });
                        pickupLocationSelect.disabled = false;
                    }
                }
            }
        } catch (error) {
            console.error('Ошибка загрузки пунктов выдачи:', error);
        }
    }

    async loadDeliveryPrice() {
        if (!this.selectedCity || this.deliveryType !== 'delivery') return;
        
        try {
            const response = await fetch(`/api/pickup-locations?type=delivery&city=${encodeURIComponent(this.selectedCity)}`);
            const locations = await response.json();
            
            if (locations.length > 0) {
                this.deliveryPrice = locations[0].delivery_price || 0;
                
                if (typeof window.updateDeliveryPriceUI === 'function') {
                    window.updateDeliveryPriceUI(this.deliveryPrice);
                } else {
                    const deliveryPriceElement = document.getElementById('delivery-price-amount');
                    if (deliveryPriceElement) {
                        deliveryPriceElement.textContent = this.deliveryPrice;
                    }
                }
            }
        } catch (error) {
            console.error('Ошибка загрузки стоимости доставки:', error);
        }
    }

    async loadUserBalance() {
        try {
            const response = await fetch('/api/user/profile');
            const data = await response.json();
            this.userBalance = data.balance || 0;
            this.updateBalancePayment();
        } catch (error) {
            console.error('Ошибка загрузки баланса:', error);
        }
    }

    selectCity(city) {
        console.log('selectCity вызван с городом:', city);
        this.selectedCity = city;
        
        if (typeof window.updateSelectedCityUI === 'function') {
            window.updateSelectedCityUI(city);
        } else {
            const cityButtons = document.querySelectorAll('.city-btn');
            cityButtons.forEach(btn => {
                if (btn.textContent === city) {
                    btn.classList.add('active');
                } else {
                    btn.classList.remove('active');
                }
            });
            
            const cityInfo = document.getElementById('city-info');
            const selectedCityName = document.getElementById('selected-city-name');
            if (cityInfo && selectedCityName) {
                selectedCityName.textContent = city;
                cityInfo.style.display = 'block';
            }
            
            this.updateNextCityButton();
        }
        
        this.updateOrderSummary();
    }

    updateNextCityButton() {
        const nextBtn = document.getElementById('next-city-btn');
        if (nextBtn) {
            nextBtn.disabled = !this.selectedCity;
            console.log('Кнопка "Далее" обновлена, disabled:', !this.selectedCity);
        }
    }

    showOrderStep(stepId) {
        console.log('Показываем шаг:', stepId);
        
        if (typeof window.showOrderStepUI === 'function') {
            window.showOrderStepUI(stepId);
        } else {
            document.querySelectorAll('.order-step').forEach(step => {
                step.style.display = 'none';
                step.classList.remove('active');
            });
            
            const step = document.getElementById(`step-${stepId}`);
            if (step) {
                step.style.display = 'block';
                step.classList.add('active');
                this.currentOrderStep = stepId;
            }
        }
        
        this.currentOrderStep = stepId;
        
        if (stepId === 'city') {
            this.updateNextCityButton();
        }
        
        if (stepId === 'summary') {
            this.updateVerificationWarning();
        }
    }

    nextOrderStep(nextStepId) {
        console.log('Переход к шагу:', nextStepId, 'Текущий шаг:', this.currentOrderStep);
        
        if (!this.validateCurrentStep()) {
            console.log('Валидация не пройдена для шага:', this.currentOrderStep);
            return;
        }
        
        this.updateOrderSummary();
        this.showOrderStep(nextStepId);
        
        if (nextStepId === 'city') {
            this.updateNextCityButton();
        }
        
        if (nextStepId === 'location') {
            if (this.deliveryType === 'pickup') {
                this.loadPickupLocations();
            }
            this.updateDeliveryInfo();
        }
        
        if (nextStepId === 'summary') {
            this.updateVerificationWarning();
        }
    }

    prevOrderStep(prevStepId) {
        console.log('Возврат к шагу:', prevStepId);
        this.showOrderStep(prevStepId);
    }

    validateCurrentStep() {
        console.log('Валидация шага:', this.currentOrderStep, 'выбранный город:', this.selectedCity);
        
        switch(this.currentOrderStep) {
            case 'customer':
                const name = document.getElementById('customer-name');
                const phone = document.getElementById('customer-phone');
                
                if (!name || !phone) return true;
                
                if (!name.value.trim()) {
                    this.showErrorNotification('Введите ваше имя', 'customer-name');
                    return false;
                }
                if (!phone.value.trim()) {
                    this.showErrorNotification('Введите номер телефона', 'customer-phone');
                    return false;
                }
                return true;
                
            case 'city':
                console.log('Проверка города:', this.selectedCity);
                if (!this.selectedCity) {
                    this.showErrorNotification('Выберите город');
                    return false;
                }
                return true;
                
            case 'location':
                if (this.deliveryType === 'pickup') {
                    const pickupLocation = document.getElementById('pickup-location');
                    if (!pickupLocation || !pickupLocation.value) {
                        this.showErrorNotification('Выберите пункт выдачи', 'pickup-location');
                        return false;
                    }
                } else {
                    const deliveryAddress = document.getElementById('delivery-address');
                    if (!deliveryAddress || !deliveryAddress.value.trim()) {
                        this.showErrorNotification('Введите адрес доставки', 'delivery-address');
                        return false;
                    }
                }
                return true;
        }
        return true;
    }

    showErrorNotification(message, fieldId = null) {
        this.showNotification(message, 'error');
        
        if (fieldId) {
            const field = document.getElementById(fieldId);
            if (field) {
                field.style.borderColor = '#ff4444';
                setTimeout(() => {
                    field.style.borderColor = '';
                }, 2000);
            }
        }
    }

    setDeliveryType(type) {
        console.log('Установка типа доставки:', type);
        this.deliveryType = type;
        
        const deliveryButtons = document.querySelectorAll('.delivery-type-btn');
        deliveryButtons.forEach(btn => {
            if (btn.dataset.type === type) {
                btn.classList.add('active');
            } else {
                btn.classList.remove('active');
            }
        });
        
        const pickupSection = document.getElementById('pickup-section');
        const deliverySection = document.getElementById('delivery-section');
        
        if (pickupSection) pickupSection.style.display = type === 'pickup' ? 'block' : 'none';
        if (deliverySection) deliverySection.style.display = type === 'delivery' ? 'block' : 'none';
        
        this.updateDeliveryInfo();
    }

    updateDeliveryInfo() {
        console.log('Обновление информации о доставке, тип:', this.deliveryType, 'город:', this.selectedCity);
        if (this.deliveryType === 'delivery' && this.selectedCity) {
            this.loadDeliveryPrice();
        } else {
            this.deliveryPrice = 0;
        }
        this.updateOrderSummary();
    }

    calculateLoyaltyCashback(amount) {
        const LOYALTY_LEVELS = [
            { min: 0, max: 10000, rate: 0.005, name: 'Новичок' },
            { min: 10000, max: 20000, rate: 0.01, name: 'Лояльный' },
            { min: 20000, max: 30000, rate: 0.02, name: 'Постоянный' },
            { min: 30000, max: 40000, rate: 0.03, name: 'Премиум' },
            { min: 40000, max: 50000, rate: 0.05, name: 'VIP' },
            { min: 50000, max: Infinity, rate: 0.05, name: 'Элита' }
        ];
        
        let cashbackRate = 0.005;
        let levelName = "Новичок";
        
        for (const level of LOYALTY_LEVELS) {
            if (amount >= level.min && amount < level.max) {
                cashbackRate = level.rate;
                levelName = level.name;
                break;
            }
        }
        
        const cashbackAmount = amount * cashbackRate;
        
        return {
            rate: cashbackRate,
            amount: cashbackAmount,
            level: levelName,
            percent: (cashbackRate * 100).toFixed(1)
        };
    }

    updateLoyaltyCashback(amount) {
        const cashbackData = this.calculateLoyaltyCashback(amount);
        const cashbackAmount = document.getElementById('cashback-amount');
        if (cashbackAmount) {
            cashbackAmount.textContent = cashbackData.amount.toFixed(2) + ' руб.';
        }
    }

    updateBalancePayment() {
        const useBalanceCheckbox = document.getElementById('use-balance-checkbox');
        const remainingBalance = document.getElementById('remaining-balance');
        const remainingAmount = document.getElementById('remaining-amount');
        const checkoutBtn = document.getElementById('checkout-btn');
        
        if (useBalanceCheckbox && remainingBalance && remainingAmount && checkoutBtn) {
            if (useBalanceCheckbox.checked) {
                const total = this.cart.total || 0;
                const remaining = this.userBalance - total;
                
                if (remaining < 0) {
                    checkoutBtn.disabled = true;
                    remainingBalance.style.display = 'block';
                    remainingAmount.textContent = 'Недостаточно средств';
                    remainingAmount.style.color = '#ff4444';
                } else {
                    checkoutBtn.disabled = false;
                    remainingBalance.style.display = 'block';
                    remainingAmount.textContent = remaining.toFixed(2) + ' руб.';
                    remainingAmount.style.color = '#00ff88';
                }
            } else {
                checkoutBtn.disabled = false;
                remainingBalance.style.display = 'none';
            }
        }
        
        const useBalanceFinal = document.getElementById('use-balance-final');
        if (useBalanceFinal) {
            const cartTotal = this.cart.total || 0;
            const deliveryPrice = this.deliveryPrice || 0;
            const total = cartTotal + deliveryPrice;
            
            if (useBalanceFinal.checked && this.userBalance < total) {
                useBalanceFinal.checked = false;
                this.showNotification('Недостаточно средств на балансе', 'error');
            }
        }
    }

    updateOrderSummary() {
        console.log('Обновление сводки заказа');
        
        const orderData = {
            cart: this.cart,
            deliveryPrice: this.deliveryPrice,
            deliveryType: this.deliveryType,
            selectedCity: this.selectedCity
        };
        
        if (typeof window.updateOrderSummaryUI === 'function') {
            window.updateOrderSummaryUI(orderData);
        }
        
        if (typeof window.updateOrderDetailsSummaryUI === 'function') {
            window.updateOrderDetailsSummaryUI(orderData);
        }
    }

    async submitOrder(e) {
        if (e) e.preventDefault();
        
        console.log('Отправка заказа, текущий шаг:', this.currentOrderStep);
        
        if (!this.validateCurrentStep()) {
            console.log('Валидация не пройдена перед отправкой');
            return;
        }
        
        const isVerified = await this.checkVerification();
        if (!isVerified) {
            this.showErrorNotification('Вы не верифицированы. Обратитесь к администратору @Danil_623');
            return;
        }
        
        const customerName = document.getElementById('customer-name');
        const customerPhone = document.getElementById('customer-phone');
        const pickupLocationSelect = document.getElementById('pickup-location');
        const deliveryAddress = document.getElementById('delivery-address');
        const useBalanceCheckbox = document.getElementById('use-balance-checkbox');
        const useBalanceFinal = document.getElementById('use-balance-final');
        
        if (!customerName || !customerPhone) return;
        
        const formData = {
            customer_name: customerName.value,
            customer_phone: customerPhone.value,
            delivery_type: this.deliveryType,
            delivery_city: this.selectedCity,
            use_balance: false
        };
        
        if (this.deliveryType === 'pickup') {
            if (!pickupLocationSelect || !pickupLocationSelect.value) {
                this.showErrorNotification('Выберите пункт выдачи');
                return;
            }
            formData.pickup_location_id = pickupLocationSelect.value;
        } else if (this.deliveryType === 'delivery') {
            if (!deliveryAddress || !deliveryAddress.value.trim()) {
                this.showErrorNotification('Введите адрес доставки');
                return;
            }
            formData.delivery_address = deliveryAddress.value.trim();
        }
        
        if (!formData.customer_name || !formData.customer_phone || !formData.delivery_city) {
            this.showErrorNotification('Заполните все обязательные поля');
            return;
        }
        
        const cartTotal = this.cart.total || 0;
        const total = cartTotal + this.deliveryPrice;
        
        if (useBalanceCheckbox && useBalanceCheckbox.checked) {
            if (this.userBalance < total) {
                this.showErrorNotification('Недостаточно средств на балансе');
                return;
            }
            formData.use_balance = true;
        }
        
        if (useBalanceFinal && useBalanceFinal.checked) {
            if (this.userBalance < total) {
                this.showErrorNotification('Недостаточно средств на балансе');
                return;
            }
            formData.use_balance = true;
        }
        
        try {
            const response = await fetch('/api/order/create', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(formData)
            });
            
            const result = await response.json();
            
            if (result.success) {
                this.showNotification(result.message || 'Заказ успешно оформлен');
                this.closeModal();
                setTimeout(() => {
                    window.location.href = '/profile';
                }, 2000);
            } else {
                this.showErrorNotification(result.error || 'Ошибка оформления заказа');
            }
        } catch (error) {
            console.error('Ошибка:', error);
            this.showErrorNotification('Ошибка оформления заказа');
        }
    }

    closeModal() {
        const modal = document.getElementById('order-modal');
        if (modal) {
            modal.style.display = 'none';
        }
    }

    showNotification(message, type = 'success') {
        const existingNotifications = document.querySelectorAll('.notification');
        existingNotifications.forEach(notification => notification.remove());
        
        const notification = document.createElement('div');
        notification.className = `notification ${type}`;
        notification.textContent = message;
        notification.style.cssText = `
            position: fixed;
            top: 20px;
            right: 20px;
            background: ${type === 'success' ? '#00ff88' : '#ff4444'};
            color: ${type === 'success' ? '#000' : '#fff'};
            padding: 15px 25px;
            border-radius: 10px;
            z-index: 10000;
            font-weight: bold;
            text-align: center;
            box-shadow: 0 5px 15px rgba(0,0,0,0.3);
            transform: translateX(400px);
            transition: transform 0.3s ease-in-out;
            max-width: 300px;
            word-wrap: break-word;
        `;
        
        document.body.appendChild(notification);
        
        setTimeout(() => {
            notification.style.transform = 'translateX(0)';
        }, 100);
        
        setTimeout(() => {
            notification.style.transform = 'translateX(400px)';
            setTimeout(() => {
                if (notification.parentNode) {
                    notification.parentNode.removeChild(notification);
                }
            }, 300);
        }, 3000);
    }
}

const vapeShop = new VapeShop();

function addToCart(productId) {
    vapeShop.addToCart(productId);
}

function updateQuantity(productId, quantity) {
    vapeShop.updateQuantity(productId, quantity);
}

function removeFromCart(productId) {
    vapeShop.removeFromCart(productId);
}

function openOrderModal() {
    vapeShop.openOrderModal();
}

function closeModal() {
    vapeShop.closeModal();
}

function selectCity(city) {
    vapeShop.selectCity(city);
}

function setDeliveryType(type) {
    vapeShop.setDeliveryType(type);
}

function showOrderStep(stepId) {
    vapeShop.showOrderStep(stepId);
}

function nextOrderStep(nextStepId) {
    vapeShop.nextOrderStep(nextStepId);
}

function prevOrderStep(prevStepId) {
    vapeShop.prevOrderStep(prevStepId);
}